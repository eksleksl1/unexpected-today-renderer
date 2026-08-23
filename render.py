import asyncio, json, re, subprocess, sys, textwrap
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
def slide(text,path):
    im=Image.new("RGB",(W,H),(12,12,13));d=ImageDraw.Draw(im);f=font(48,True);lines=textwrap.wrap(text,width=20,break_long_words=True,break_on_hyphens=False);y=max(180,(H-len(lines)*78)//2-80)
    for line in lines:
        box=d.textbbox((0,0),line,font=f);d.text(((W-(box[2]-box[0]))//2,y),line,font=f,fill=(242,242,242));y+=78
    d.text((70,H-110),"뜻밖의 오늘",font=font(28,True),fill=(197,226,113));im.save(path)
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
Style: Default,NanumGothic,54,&H00FFFFFF,&H0000FFFF,&H00101010,&H90000000,-1,0,0,0,100,100,0,0,1,4,1,2,70,70,170,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    Path(out).write_text(header+"\n".join(f"Dialogue: 0,{t(a)},{t(b)},Default,,0,0,0,,{re.sub(r'<[^>]+>','',txt)}" for a,b,txt in cues),encoding="utf-8-sig")
def main(job_path):
    job=json.loads(Path(job_path).read_text(encoding="utf-8"));WORK.mkdir(exist_ok=True);OUT.mkdir(exist_ok=True);parts=[]
    for i,text in enumerate(split(job["script"])):
        base=WORK/f"part-{i:03d}";png=base.with_suffix(".png");mp3=base.with_suffix(".mp3");vtt=base.with_suffix(".vtt");sub=base.with_suffix(".ass");mp4=base.with_suffix(".mp4")
        slide(text,png);asyncio.run(voice(text,mp3,vtt));ass(vtt,sub);length=duration(mp3)+.25
        run(["ffmpeg","-y","-loop","1","-framerate",str(FPS),"-i",png,"-i",mp3,"-vf",f"subtitles={sub},fade=t=in:st=0:d=.12,fade=t=out:st={max(0,length-.12):.3f}:d=.12","-t",f"{length:.3f}","-r",str(FPS),"-c:v","libx264","-preset","veryfast","-crf","21","-pix_fmt","yuv420p","-c:a","aac","-b:a","160k","-shortest",mp4]);parts.append(mp4)
    listing=WORK/"concat.txt";listing.write_text("\n".join(f"file '{p.as_posix()}'" for p in parts),encoding="utf-8");run(["ffmpeg","-y","-f","concat","-safe","0","-i",listing,"-c","copy",OUT/"result.mp4"])
if __name__=="__main__":main(sys.argv[1] if len(sys.argv)>1 else ROOT/"job.json")
