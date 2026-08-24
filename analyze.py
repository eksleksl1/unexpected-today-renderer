import asyncio, json, re, sys
from pathlib import Path
from render import download, classify, frames_for, voice, ocr_words

ROOT=Path(__file__).parent.resolve();OUT=ROOT/"analysis-output"
def tokens(text):return set(re.findall(r"[0-9A-Za-z가-힣]{2,}",text.lower()))
def scene_mapping(script,frame_texts):
    scenes=[x.strip() for x in re.split(r"\n\s*\n",script) if x.strip()];mapping=[];matched=0
    for i,scene in enumerate(scenes):
        st=tokens(scene);scores=[]
        for j,value in enumerate(frame_texts):
            ft=tokens(value);scores.append((len(st&ft)/max(1,min(len(st),len(ft))),-abs(j-i*len(frame_texts)/max(1,len(scenes)))))
        best=max(range(len(scores)),key=lambda j:scores[j]) if scores else 0
        if scores and scores[best][0]>=.08:matched+=1
        else:best=min(len(frame_texts)-1,int(i*len(frame_texts)/max(1,len(scenes))))
        mapping.append(best)
    return mapping,matched/max(1,len(scenes))
def main(job_path):
    job=json.loads(Path(job_path).read_text(encoding="utf-8"));OUT.mkdir(exist_ok=True);frames=[];rejected=0;modes=[];seen=set()
    for url in job.get("image_urls") or []:
        try:
            photo=download(url)
            if photo.width<480 or photo.height<320:rejected+=1;continue
            thumb=photo.convert("L").resize((16,16));fingerprint=bytes(1 if value>=sum(thumb.getdata())/256 else 0 for value in thumb.getdata())
            if fingerprint in seen:rejected+=1;continue
            seen.add(fingerprint);kind=classify(photo);modes.append(kind)
            if kind=="derivative":rejected+=1;continue
            frames.extend(frames_for(photo,kind))
        except Exception:rejected+=1
    if len(frames)<3:raise RuntimeError("내용에 맞는 서로 다른 화면을 3장 이상 확보하지 못했습니다.")
    rewritten=job["script"].strip()
    if len(rewritten)<220:raise RuntimeError("재작성 대본 분량이 부족합니다.")
    frame_texts=[];caption_flags=[]
    for i,frame in enumerate(frames):
        photo=frame["photo"].crop(frame["box"]) if frame["box"] else frame["photo"].copy();photo.save(OUT/f"frame-{i:03d}.jpg",quality=91,optimize=True)
        try:frame_texts.append(" ".join(x[0] for x in ocr_words(photo))[:1600])
        except Exception:frame_texts.append("")
        caption_flags.append(bool(frame["caption"]))
    ev=tokens(job.get("evidence","")+" "+job.get("title",""));kept=[]
    for i,value in enumerate(frame_texts):
        ft=tokens(value)
        if not ft or len(ft)<5 or ft&ev:kept.append(i)
    if len(kept)<3:raise RuntimeError("본문과 의미가 연결되는 화면을 3장 이상 확보하지 못했습니다.")
    if len(kept)!=len(frames):
        for new,old in enumerate(kept):(OUT/f"frame-{old:03d}.jpg").replace(OUT/f"kept-{new:03d}.jpg")
        for path in OUT.glob("frame-*.jpg"):path.unlink()
        for path in OUT.glob("kept-*.jpg"):path.replace(OUT/path.name.replace("kept-","frame-"))
        frame_texts=[frame_texts[i] for i in kept];caption_flags=[caption_flags[i] for i in kept];frames=[frames[i] for i in kept]
    (OUT/"script.txt").write_text(rewritten,encoding="utf-8")
    asyncio.run(voice(rewritten,OUT/"preview.mp3",OUT/"preview.vtt"))
    mapping,coverage=scene_mapping(rewritten,frame_texts)
    if any(frame_texts) and coverage<.25:raise RuntimeError("대본 장면과 이미지 내용의 연결성이 부족합니다.")
    (OUT/"manifest.json").write_text(json.dumps({"frames":len(frames),"rejected":rejected,"modes":modes,"frameTexts":frame_texts,"captionFlags":caption_flags,"sceneFrames":mapping,"semanticCoverage":coverage},ensure_ascii=False),encoding="utf-8")
if __name__=="__main__":main(sys.argv[1] if len(sys.argv)>1 else ROOT/"job.json")
