import asyncio, json, re, sys
from pathlib import Path
from render import download, classify, frames_for, voice, ocr_words, font
from PIL import Image, ImageDraw

ROOT=Path(__file__).parent.resolve();OUT=ROOT/"analysis-output"
def tokens(text):return set(re.findall(r"[0-9A-Za-z가-힣]{2,}",text.lower()))
def related(text,evidence):
    left=tokens(text);right=tokens(evidence)
    if left&right:return True
    a=re.sub(r"[^0-9A-Za-z가-힣]","",text.lower());b=re.sub(r"[^0-9A-Za-z가-힣]","",evidence.lower())
    grams={a[i:i+2] for i in range(max(0,len(a)-1))};return len(grams&{b[i:i+2] for i in range(max(0,len(b)-1))})>=2
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
def wrap_text(draw,text,face,width):
    lines=[];current=""
    for ch in re.sub(r"\s+"," ",text).strip():
        trial=current+ch
        if current and draw.textbbox((0,0),trial,font=face)[2]>width:lines.append(current.strip());current=ch
        else:current=trial
    if current.strip():lines.append(current.strip())
    return lines
def scene_symbol(draw,text,accent):
    cx,cy=540,260;ink=(45,51,62);lower=text.lower()
    if re.search(r"강아지|고양이|동물|반려",lower):
        draw.ellipse((cx-105,cy-90,cx+105,cy+110),fill=accent);draw.polygon([(cx-90,cy-55),(cx-150,cy-145),(cx-35,cy-105)],fill=accent);draw.polygon([(cx+90,cy-55),(cx+150,cy-145),(cx+35,cy-105)],fill=accent);draw.ellipse((cx-45,cy-10,cx-20,cy+15),fill=ink);draw.ellipse((cx+20,cy-10,cx+45,cy+15),fill=ink)
    elif re.search(r"차|자동차|운전|도로|주차",lower):
        draw.rounded_rectangle((cx-190,cy-55,cx+190,cy+80),radius=30,fill=accent);draw.polygon([(cx-110,cy-55),(cx-55,cy-125),(cx+85,cy-125),(cx+145,cy-55)],fill=accent);draw.ellipse((cx-135,cy+48,cx-65,cy+118),fill=ink);draw.ellipse((cx+65,cy+48,cx+135,cy+118),fill=ink)
    elif re.search(r"회사|직장|학교|가게|식당|병원",lower):
        draw.rounded_rectangle((cx-150,cy-145,cx+150,cy+125),radius=18,fill=accent);draw.rectangle((cx-35,cy+25,cx+35,cy+125),fill=ink)
        for x in (-95,0,95):draw.rectangle((cx+x-24,cy-85,cx+x+24,cy-35),fill=(242,246,244))
    elif re.search(r"휴대폰|핸드폰|문자|메시지|앱|온라인",lower):
        draw.rounded_rectangle((cx-105,cy-165,cx+105,cy+165),radius=28,fill=ink);draw.rounded_rectangle((cx-82,cy-125,cx+82,cy+110),radius=12,fill=accent);draw.ellipse((cx-15,cy+130,cx+15,cy+160),fill=accent)
    else:
        draw.ellipse((cx-70,cy-145,cx+70,cy-5),fill=accent);draw.rounded_rectangle((cx-155,cy+5,cx+155,cy+175),radius=75,fill=accent);draw.ellipse((cx-42,cy-92,cx-20,cy-70),fill=ink);draw.ellipse((cx+20,cy-92,cx+42,cy-70),fill=ink)
def community_card(title,scene,index,total):
    im=Image.new("RGB",(1080,940),(238,242,240));d=ImageDraw.Draw(im);accent=[(89,188,132),(93,143,214),(224,150,76),(161,112,204)][index%4]
    d.rounded_rectangle((52,36,1028,904),radius=38,fill=(255,255,255),outline=(215,224,219),width=3);d.ellipse((92,78,166,152),fill=accent);d.text((188,76),"익명 커뮤니티",font=font(34,True),fill=(28,35,32));d.text((188,119),f"사연 재구성 · {index+1}/{total}",font=font(24),fill=(121,132,127));d.line((88,180,992,180),fill=(226,232,229),width=2)
    scene_symbol(d,scene,accent);d.rounded_rectangle((88,490,992,848),radius=28,fill=(247,249,248));title_face=font(38,True);body_face=font(34)
    y=525
    for line in wrap_text(d,title,title_face,820)[:2]:d.text((130,y),line,font=title_face,fill=(28,35,32));y+=50
    y+=20
    for line in wrap_text(d,scene,body_face,820)[:5]:d.text((130,y),line,font=body_face,fill=(56,64,60));y+=47
    return im
def main(job_path):
    job=json.loads(Path(job_path).read_text(encoding="utf-8"));OUT.mkdir(exist_ok=True);rewritten=job["script"].strip()
    if len(rewritten)<220:raise RuntimeError("재작성 대본 분량이 부족합니다.")
    if job.get("content_mode")=="community":
        scenes=[x.strip() for x in re.split(r"\n\s*\n",rewritten) if x.strip()]
        if len(scenes)<3:raise RuntimeError("재구성할 장면이 부족합니다.")
        for i,scene in enumerate(scenes):community_card(job.get("title","커뮤니티 사연"),scene,i,len(scenes)).save(OUT/f"frame-{i:03d}.jpg",quality=92,optimize=True)
        (OUT/"script.txt").write_text(rewritten,encoding="utf-8");asyncio.run(voice(rewritten,OUT/"preview.mp3",OUT/"preview.vtt"))
        (OUT/"manifest.json").write_text(json.dumps({"frames":len(scenes),"rejected":0,"modes":["reconstructed-community"],"frameTexts":scenes,"captionFlags":[False]*len(scenes),"sceneFrames":list(range(len(scenes))),"semanticCoverage":1,"reconstructed":True},ensure_ascii=False),encoding="utf-8");return
    frames=[];rejected=0;modes=[];seen=set()
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
    frame_texts=[];caption_flags=[]
    for i,frame in enumerate(frames):
        photo=frame["photo"].crop(frame["box"]) if frame["box"] else frame["photo"].copy();photo.save(OUT/f"frame-{i:03d}.jpg",quality=91,optimize=True)
        try:frame_texts.append(" ".join(x[0] for x in ocr_words(photo))[:1600])
        except Exception:frame_texts.append("")
        caption_flags.append(bool(frame["caption"]))
    evidence=job.get("evidence","")+" "+job.get("title","");kept=[]
    for i,value in enumerate(frame_texts):
        ft=tokens(value)
        if not ft or len(ft)<5 or related(value,evidence):kept.append(i)
    if len(kept)<3:raise RuntimeError("본문과 의미가 연결되는 화면을 3장 이상 확보하지 못했습니다.")
    if len(kept)!=len(frames):
        for new,old in enumerate(kept):(OUT/f"frame-{old:03d}.jpg").replace(OUT/f"kept-{new:03d}.jpg")
        for path in OUT.glob("frame-*.jpg"):path.unlink()
        for path in OUT.glob("kept-*.jpg"):path.replace(OUT/path.name.replace("kept-","frame-"))
        frame_texts=[frame_texts[i] for i in kept];caption_flags=[caption_flags[i] for i in kept];frames=[frames[i] for i in kept]
    (OUT/"script.txt").write_text(rewritten,encoding="utf-8")
    asyncio.run(voice(rewritten,OUT/"preview.mp3",OUT/"preview.vtt"))
    mapping,coverage=scene_mapping(rewritten,frame_texts)
    (OUT/"manifest.json").write_text(json.dumps({"frames":len(frames),"rejected":rejected,"modes":modes,"frameTexts":frame_texts,"captionFlags":caption_flags,"sceneFrames":mapping,"semanticCoverage":coverage},ensure_ascii=False),encoding="utf-8")
if __name__=="__main__":main(sys.argv[1] if len(sys.argv)>1 else ROOT/"job.json")
