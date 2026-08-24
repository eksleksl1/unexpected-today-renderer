import asyncio, json, sys
from pathlib import Path
from render import download, classify, frames_for, voice

ROOT=Path(__file__).parent.resolve();OUT=ROOT/"analysis-output"
def main(job_path):
    job=json.loads(Path(job_path).read_text(encoding="utf-8"));OUT.mkdir(exist_ok=True);frames=[];rejected=0;modes=[]
    for url in job.get("image_urls") or []:
        try:
            photo=download(url);kind=classify(photo);modes.append(kind)
            if kind=="derivative":rejected+=1;continue
            frames.extend(frames_for(photo,kind))
        except Exception:rejected+=1
    if not frames:raise RuntimeError("자막 없는 원본 이미지를 찾지 못했습니다.")
    rewritten=job["script"].strip()
    if len(rewritten)<220:raise RuntimeError("재작성 대본 분량이 부족합니다.")
    for i,frame in enumerate(frames):
        photo=frame["photo"].crop(frame["box"]) if frame["box"] else frame["photo"].copy();photo.save(OUT/f"frame-{i:03d}.jpg",quality=91,optimize=True)
    (OUT/"script.txt").write_text(rewritten,encoding="utf-8")
    asyncio.run(voice(rewritten,OUT/"preview.mp3",OUT/"preview.vtt"))
    (OUT/"manifest.json").write_text(json.dumps({"frames":len(frames),"rejected":rejected,"modes":modes},ensure_ascii=False),encoding="utf-8")
if __name__=="__main__":main(sys.argv[1] if len(sys.argv)>1 else ROOT/"job.json")
