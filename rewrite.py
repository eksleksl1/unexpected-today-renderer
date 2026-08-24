import re
from difflib import SequenceMatcher

MODEL="Qwen/Qwen3-1.7B"

def clean_output(text):
    text=re.sub(r"^(?:대본|내레이션|쇼츠 대본)\s*[:：-]?\s*","",text.strip(),flags=re.I)
    text=re.sub(r"(?:원문|출처|제공된 글)(?:을|에)?\s*(?:따르면|기반으로).*?(?:\n|$)","",text)
    text=text.replace("###","").replace("**","").strip()
    return re.sub(r"\n{3,}","\n\n",text)

def rewrite_script(title,source):
    from transformers import AutoModelForCausalLM,AutoTokenizer
    tokenizer=AutoTokenizer.from_pretrained(MODEL)
    model=AutoModelForCausalLM.from_pretrained(MODEL,torch_dtype="auto",device_map="cpu")
    prompt=f"""너는 한국 유튜브 쇼츠 전문 작가다. 아래 커뮤니티 글을 그대로 복사하지 말고 사실관계만 사용해 완전히 새로운 한국어 내레이션 대본을 작성하라.

규칙:
- 35~50초 분량, 250~450자, 6~9문장
- 첫 1~2문장은 궁금증을 만드는 훅
- 상황, 핵심 전개, 반응 또는 결론 순서
- 같은 뜻을 새 문장 구조와 자연스러운 구어체로 재구성
- 원문에 직접 등장하지 않은 인물, 장소, 물건, 사건은 절대 추가하지 않기
- 각 문장은 반드시 본문의 구체적인 근거를 하나 이상 포함하기
- '원문', '확인된 내용', '후보', '영상화', '출처에 따르면' 같은 메타 표현 금지
- 안내문, 사이트 메뉴, 저작권 문구, 날짜, 조회수, 닉네임 제거
- 제목이나 문장을 반복하지 말고 대본만 출력

제목: {title}
본문:
{source[:2400]}
"""
    system="원문에 명시된 사실만 사용하고 추측이나 창작을 하지 않는 한국어 쇼츠 작가다."
    messages=[{"role":"system","content":system},{"role":"user","content":prompt}]
    inputs=tokenizer.apply_chat_template(messages,tokenize=False,add_generation_prompt=True,enable_thinking=False)
    encoded=tokenizer([inputs],return_tensors="pt")
    generated=model.generate(**encoded,max_new_tokens=520,do_sample=False,repetition_penalty=1.08)
    output=clean_output(tokenizer.batch_decode(generated[:,encoded.input_ids.shape[1]:],skip_special_tokens=True)[0])
    original=re.sub(r"\s+","",source);ratio=SequenceMatcher(None,re.sub(r"\s+","",output),original).ratio()
    stop={"그리고","하지만","그래서","이번","대한","하는","했다","있다","없다","정도","모습","내용","사람","사진"}
    source_tokens=set(re.findall(r"[가-힣A-Za-z0-9]{2,}",source))-stop
    unsupported=[]
    for sentence in re.split(r"(?<=[.!?。])\s+|\n+",output):
        tokens=(set(re.findall(r"[가-힣A-Za-z0-9]{2,}",sentence))-stop)
        if len(tokens)>=3 and len(tokens&source_tokens)/len(tokens)<.16:unsupported.append(sentence)
    if not 180<=len(output)<=850 or ratio>.82 or unsupported:
        raise RuntimeError(f"근거 기반 재작성 기준 미달: length={len(output)}, similarity={ratio:.3f}, unsupported={unsupported[:2]}, draft={output[:600]}")
    return output
