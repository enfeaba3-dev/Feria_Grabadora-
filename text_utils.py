import re


def _normalized_word(value:str)->str:
    return re.sub(r'[^\wáéíóúüñ]+','',value.lower(),flags=re.UNICODE)


def merge_transcript(existing:str,incoming:str,max_overlap:int=12)->tuple[str,int]:
    existing=' '.join((existing or '').split()).strip()
    incoming=' '.join((incoming or '').split()).strip()
    if not incoming:
        return existing,0
    if not existing:
        return incoming,0
    old_words=existing.split()
    new_words=incoming.split()
    overlap=0
    for size in range(min(max_overlap,len(old_words),len(new_words)),0,-1):
        left=[_normalized_word(word) for word in old_words[-size:]]
        right=[_normalized_word(word) for word in new_words[:size]]
        if left==right and all(left):
            overlap=size
            break
    remainder=' '.join(new_words[overlap:]).strip()
    return (f'{existing} {remainder}'.strip() if remainder else existing),overlap
