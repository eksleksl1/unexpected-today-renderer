import asyncio, csv, io, json, re, subprocess, sys, tempfile, textwrap, urllib.request
from pathlib import Path
import edge_tts
from PIL import Image, ImageDraw, ImageFont, ImageStat

ROOT=Path(__file__).parent.resolve();WORK=ROOT/"work";OUT=ROOT/"output";W,H,FPS=1080,1920,30;VY,VH=520,940
def run(cmd):subprocess.run([str(x) for x in cmd],check=True)
def duration(path):return float(subprocess.check_output(["ffprobe","-v","error","-show_entries","format=duration","-of","default=nw=1:nk=1",str(path)],text=True).strip())
def font(size,bold=False):return ImageFont.truetype("/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf" if bold else "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",size)
def download(url):
    req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 UnexpectedToday/1.0"});return Image.open(io.BytesIO(urllib.request.urlopen(req,timeout=25).read())).convert("RGB")
def ocr_words(photo):
    sample=photo.copy();sample.thumbnail((1500,2200))
    with tempfile.NamedTemporaryFile(suffix=".png") as f:
        sample.save(f.name);raw=subprocess.run(["tesseract",f.name,"stdout","-l","kor+eng","--psm","6","tsv"],capture_output=True,text=True,timeout=35).stdout
    rows=[]
    for row in csv.DictReader(io.StringIO(raw),delimiter="\t"):
        try:
            text=re.sub(r"\s+","",row.get("text", ""));conf=float(row.get("conf",-1))
            if conf>=35 and re.search(r"[0-9A-Za-z가-힣]",text):rows.append((text,int(row["left"]),int(row["top"]),int(row["width"]),int(row["height"]),sample.width,sample.height))
        except Exception:pass
    return rows
def classify(photo):
    try:words=ocr_words(photo)
    except Exception:words=[]
    small=photo.copy();small.thumbnail((240,240));gray=small.convert("L");hist=gray.histogram();total=sum(hist);light=sum(hist[225:])/max(1,total)
    bands={min(5,int((top+h/2)/max(1,sh)*6)) for _,_,top,_,h,_,sh in words};chars=sum(len(w[0]) for w in words)
    document=(len(words)>=12 and len(bands)>=3 and (light>.34 or chars>=80)) or len(words)>=28
    derivative=(not document and len(words)>=4 and chars>=12 and len(bands)<=3)
    return "document" if document else "derivative" if derivative else "clean"
def natural_cut(photo,start,window):
    ideal=min(photo.height,start+window);lo=max(start+int(window*.72),ideal-int(window*.16));hi=min(photo.height,ideal+int(window*.12))
    if hi<=lo:return ideal
    gray=photo.convert("L").resize((220,photo.height));best=(10**9,ideal)
    for y in range(lo,hi+1,max(2,(hi-lo)//80 or 2)):
        band=gray.crop((0,max(0,y-4),220,min(gray.height,y+5)));stat=ImageStat.Stat(band);score=(255-stat.mean[0])+stat.stddev[0]*1.8
        if score<best[0]:best=(score,y)
    return best[1]
def frames_for(photo,kind):
    if kind=="derivative":return []
    source_window=max(1,int(VH*photo.width/W))
    if kind!="document" or photo.height<=source_window*1.12:return [{"photo":photo,"box":None,"caption":kind=="clean"}]
    frames=[];top=0;overlap=max(12,int(source_window*.045))
    while top<photo.height-20:
        cut=natural_cut(photo,top,source_window);cut=min(photo.height,max(top+int(source_window*.55),cut));frames.append({"photo":photo,"box":(0,top,photo.width,cut),"caption":False})
        if cut>=photo.height:break
        top=max(top+1,cut-overlap)
        if len(frames)>=24:break
    return frames
def prepare(urls):
    frames=[]
    for url in urls:
        try:
            photo=download(url);frames.extend(frames_for(photo,classify(photo)))
        except Exception:pass
    if not frames:raise RuntimeError("자막 없는 원본 이미지를 찾지 못해 후보를 제외했습니다.")
    return frames
def split_count(text,count):
    clean=re.sub(r"\s+"," ",text).strip();units=[x.strip() for x in re.split(r"(?<=[.!?。]|다\.)\s+",clean) if x.strip()]
    if len(units)<count:units=[x.strip() for x in re.findall(r".{1,55}(?:\s|$)|.{1,55}",clean) if x.strip()]
    buckets=[];target=max(1,len(clean)//count);current=""
    for unit in units:
        if current and len(current)+len(unit)>target and len(buckets)<count-1:buckets.append(current.strip());current=unit
        else:current=(current+" "+unit).strip()
    if current:buckets.append(current)
    while len(buckets)<count:buckets.append(buckets[-1] if buckets else clean)
    return buckets[:count]
def slide(title,path,frame):
    im=Image.new("RGB",(W,H),(0,0,0));photo=frame["photo"].crop(frame["box"]) if frame["box"] else frame["photo"].copy();scale=min(W/photo.width,VH/photo.height);photo=photo.resize((max(1,int(photo.width*scale)),max(1,int(photo.height*scale))));im.paste(photo,((W-photo.width)//2,VY+(VH-photo.height)//2))
    d=ImageDraw.Draw(im);d.text((75,92),"뜻밖의 오늘",font=font(32,True),fill=(20,232,61));f=font(62,True);lines=textwrap.wrap(title,width=15,break_long_words=True,break_on_hyphens=False)[:4];y=155
    for idx,line in enumerate(lines):d.text((75,y),line,font=f,fill=(255,238,35) if idx==len(lines)-1 else (244,244,244));y+=82
    im.save(path)
async def voice(text,audio,vtt):
    talk=edge_tts.Communicate(text,"ko-KR-InJoonNeural",rate="+5%");subs=edge_tts.SubMaker()
    with open(audio,"wb") as media:
        async for chunk in talk.stream():
            if chunk["type"]=="audio":media.write(chunk["data"])
            elif chunk["type"]=="WordBoundary":subs.feed(chunk)
    Path(vtt).write_text(subs.get_webvtt(),encoding="utf-8")
def secs(x):
    h,m,s=x.split(":");return int(h)*3600+int(m)*60+float(s)
def stamp(value):
    h=int(value//3600);value-=h*3600;m=int(value//60);s=value-m*60;return f"{h}:{m:02d}:{s:05.2f}"
def ass(vtt,out):
    raw=Path(vtt).read_text(encoding="utf-8-sig");cues=re.findall(r"(\d\d:\d\d:\d\d\.\d{3}) --> (\d\d:\d\d:\d\d\.\d{3})[^\n]*\n([^\n]+)",raw);events=[]
    for a,b,txt in cues:
        txt=re.sub(r"<[^>]+>","",txt).strip();chunks=[x.strip() for x in re.findall(r".{1,22}(?:\s|$)|.{1,22}",txt) if x.strip()];start,end=secs(a),secs(b);span=max(.12,(end-start)/max(1,len(chunks)))
        for i,chunk in enumerate(chunks):
            lines=textwrap.wrap(chunk,width=11,break_long_words=True,break_on_hyphens=False)[:2];caption="\\N".join(lines);events.append(f"Dialogue: 0,{stamp(start+i*span)},{stamp(min(end,start+(i+1)*span))},Default,,0,0,0,,{caption}")
    header="""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,NanumGothic,68,&H00FFFFFF,&H0000FFFF,&H00101010,&H90000000,-1,0,0,0,100,100,0,0,1,6,1,2,105,105,565,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    Path(out).write_text(header+"\n".join(events),encoding="utf-8-sig")
def main(job_path):
    job=json.loads(Path(job_path).read_text(encoding="utf-8"));WORK.mkdir(exist_ok=True);OUT.mkdir(exist_ok=True);frames=prepare(job.get("image_urls") or []);texts=split_count(job["script"],max(len(frames),len(re.split(r"\n\s*\n",job["script"]))));parts=[]
    for i,text in enumerate(texts):
        frame=frames[min(len(frames)-1,int(i*len(frames)/len(texts)))];base=WORK/f"part-{i:03d}";png=base.with_suffix(".png");mp3=base.with_suffix(".mp3");vtt=base.with_suffix(".vtt");sub=base.with_suffix(".ass");mp4=base.with_suffix(".mp4");slide(job["title"],png,frame);asyncio.run(voice(text,mp3,vtt));ass(vtt,sub);length=duration(mp3)+.25;captions=f"subtitles={sub}," if frame["caption"] else ""
        run(["ffmpeg","-y","-loop","1","-framerate",str(FPS),"-i",png,"-i",mp3,"-vf",f"{captions}fade=t=in:st=0:d=.12,fade=t=out:st={max(0,length-.12):.3f}:d=.12","-t",f"{length:.3f}","-r",str(FPS),"-c:v","libx264","-preset","veryfast","-crf","21","-pix_fmt","yuv420p","-c:a","aac","-b:a","160k","-shortest",mp4]);parts.append(mp4)
    listing=WORK/"concat.txt";listing.write_text("\n".join(f"file '{p.as_posix()}'" for p in parts),encoding="utf-8");run(["ffmpeg","-y","-f","concat","-safe","0","-i",listing,"-c","copy",OUT/"result.mp4"])
if __name__=="__main__":main(sys.argv[1] if len(sys.argv)>1 else ROOT/"job.json")
