import asyncio, io, json, re, subprocess, sys, tempfile, textwrap, urllib.request
from pathlib import Path
import edge_tts
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).parent.resolve(); WORK=ROOT/"work"; OUT=ROOT/"output"; W,H,FPS=1080,1920,30
def run(cmd): subprocess.run([str(x) for x in cmd],check=True)
def duration(path): return float(subprocess.check_output(["ffprobe","-v","error","-show_entries","format=duration","-of","default=nw=1:nk=1",str(path)],text=True).strip())
def font(size,bold=False): return ImageFont.truetype("/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf" if bold else "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",size)
def split(text):
    parts=[p.strip() for p in re.split(r"\n\s*\n",text) if p.strip()]
    return parts if len(parts)>1 else [x.strip() for x in re.split(r"(?<=[.!?])\s+",text) if x.strip()]
def text_heavy(photo):
    try:
        sample=photo.copy();sample.thumbnail((1400,1400))
        with tempfile.NamedTemporaryFile(suffix=".png") as f:
            sample.save(f.name)
            result=subprocess.run(["tesseract",f.name,"stdout","-l","kor+eng","--psm","6"],capture_output=True,text=True,timeout=25)
        found=re.sub(r"[^0-9A-Za-z가-힣]","",result.stdout)
        lines=[x.strip() for x in result.stdout.splitlines() if len(re.sub(r"\s+","",x))>=4]
        return len(found)>=45 or len(lines)>=4
    except Exception:
        return photo.height>photo.width*1.35
def slide(title,path,image_url=None):
    im=Image.new("RGB",(W,H),(0,0,0)); visual_y,visual_h=520,940
    has_text=False
    if image_url:
        try:
            req=urllib.request.Request(image_url,headers={"User-Agent":"Mozilla/5.0 UnexpectedToday/1.0"});raw=urllib.request.urlopen(req,timeout=20).read();photo=Image.open(io.BytesIO(raw)).convert("RGB")
            has_text=text_heavy(photo);scale=min(W/photo.width,visual_h/photo.height);photo=photo.resize((max(1,int(photo.width*scale)),max(1,int(photo.height*scale))));left=(W-photo.width)//2;top=visual_y+(visual_h-photo.height)//2;im.paste(photo,(left,top))
        except Exception: pass
    d=ImageDraw.Draw(im);d.text((75,92),"뜻밖의 오늘",font=font(32,True),fill=(20,232,61));f=font(62,True);lines=textwrap.wrap(title,width=15,break_long_words=True,break_on_hyphens=False)[:4];y=155
    for idx,line in enumerate(lines):
        d.text((75,y),line,font=f,fill=(255,238,35) if idx==len(lines)-1 else (244,244,244));y+=82
    im.save(path);return has_text
async def voice(text,audio,vtt):
    talk=edge_tts.Communicate(text,"ko-KR-InJoonNeural",rate="+5%");subs=edge_tts.SubMaker()
    with open(audio,"wb") as media:
        async for chunk in talk.stream():
            if chunk["type"]=="audio":media.write(chunk["data"])
            elif chunk["type"]=="WordBoundary":subs.feed(chunk)
    Path(vtt).write_text(subs.get_webvtt(),encoding="utf-8")
def ass(vtt,out):
    raw=Path(vtt).read_text(encoding="utf-8-sig");cues=re.findall(r"(\d\d:\d\d:\d\d\.\d{3}) --> (\d\d:\d\d:\d\d\.\d{3})[^\n]*\n([^\n]+)",raw)
    def t(x):h,m,s=x.split(":");return f"{int(h)}:{m}:{s[:5]}"
    header="""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,NanumGothic,58,&H00FFFFFF,&H0000FFFF,&H00101010,&H90000000,-1,0,0,0,100,100,0,0,1,5,1,2,80,80,560,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    Path(out).write_text(header+"\n".join(f"Dialogue: 0,{t(a)},{t(b)},Default,,0,0,0,,{re.sub(r'<[^>]+>','',txt)}" for a,b,txt in cues),encoding="utf-8-sig")
def main(job_path):
    job=json.loads(Path(job_path).read_text(encoding="utf-8"));WORK.mkdir(exist_ok=True);OUT.mkdir(exist_ok=True);parts=[];images=job.get("image_urls") or []
    for i,text in enumerate(split(job["script"])):
        base=WORK/f"part-{i:03d}";png=base.with_suffix(".png");mp3=base.with_suffix(".mp3");vtt=base.with_suffix(".vtt");sub=base.with_suffix(".ass");mp4=base.with_suffix(".mp4")
        has_text=slide(job["title"],png,images[i%len(images)] if images else None);asyncio.run(voice(text,mp3,vtt));ass(vtt,sub);length=duration(mp3)+.25
        captions="" if has_text else f"subtitles={sub},"
        run(["ffmpeg","-y","-loop","1","-framerate",str(FPS),"-i",png,"-i",mp3,"-vf",f"{captions}fade=t=in:st=0:d=.12,fade=t=out:st={max(0,length-.12):.3f}:d=.12","-t",f"{length:.3f}","-r",str(FPS),"-c:v","libx264","-preset","veryfast","-crf","21","-pix_fmt","yuv420p","-c:a","aac","-b:a","160k","-shortest",mp4]);parts.append(mp4)
    listing=WORK/"concat.txt";listing.write_text("\n".join(f"file '{p.as_posix()}'" for p in parts),encoding="utf-8");run(["ffmpeg","-y","-f","concat","-safe","0","-i",listing,"-c","copy",OUT/"result.mp4"])
if __name__=="__main__":main(sys.argv[1] if len(sys.argv)>1 else ROOT/"job.json")
