import re
from difflib import SequenceMatcher

MODEL="Qwen/Qwen2.5-1.5B-Instruct"

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
- 40~55초 분량, 300~500자, 8~12문장
- 첫 1~2문장은 궁금증을 만드는 훅
- 상황, 핵심 전개, 반응 또는 결론 순서
- 같은 뜻을 새 문장 구조와 자연스러운 구어체로 재구성
- 원문에 없는 사실은 만들지 않기
- '원문', '확인된 내용', '후보', '영상화', '출처에 따르면' 같은 메타 표현 금지
- 안내문, 사이트 메뉴, 저작권 문구, 날짜, 조회수, 닉네임 제거
- 제목이나 문장을 반복하지 말고 대본만 출력

제목: {title}
본문:
{source[:2400]}
"""
    messages=[{"role":"system","content":"사실을 과장하거나 창작하지 않고, 원문을 새 내레이션으로 재구성하는 한국어 쇼츠 작가다."},{"role":"user","content":prompt}]
    inputs=tokenizer.apply_chat_template(messages,tokenize=False,add_generation_prompt=True)
    encoded=tokenizer([inputs],return_tensors="pt")
    generated=model.generate(**encoded,max_new_tokens=760,do_sample=True,temperature=.55,top_p=.86,repetition_penalty=1.12)
    output=tokenizer.batch_decode(generated[:,encoded.input_ids.shape[1]:],skip_special_tokens=True)[0]
    output=clean_output(output)
    compact=re.sub(r"\s+","",output);original=re.sub(r"\s+","",source)
    if len(output)<180 or len(output)>850 or SequenceMatcher(None,compact,original).ratio()>.82:
        raise RuntimeError("원문 재작성 품질 기준을 통과하지 못했습니다.")
    return output
