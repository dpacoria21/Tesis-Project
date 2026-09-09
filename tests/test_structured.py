import torch
from tutor.structured import tokenizer_data,prefix_constraint


class CharacterTokenizer:
    all_special_ids=[0]
    eos_token_id=0
    def __len__(self): return 128
    def encode(self,text,**kwargs): return [ord(c) for c in text]
    def decode(self,ids,**kwargs): return "".join(chr(i) for i in ids if i)


def test_constrained_format_requires_known_citation_and_nonempty_list():
    data=tokenizer_data(CharacterTokenizer())
    schema={"type":"object","properties":{"used_chunk_ids":{"type":"array","minItems":1,"maxItems":1,"items":{"type":"string","enum":["p:statement"]}}},"required":["used_chunk_ids"],"additionalProperties":False}
    allowed=prefix_constraint(data,schema)
    prefix=[48]
    for char in '{"used_chunk_ids":[':
        assert ord(char) in allowed(0,torch.tensor(prefix))
        prefix.append(ord(char))
    assert ord(']') not in allowed(0,torch.tensor(prefix))
    prefix.append(ord('"'))
    assert ord('f') not in allowed(0,torch.tensor(prefix))
    assert ord('p') in allowed(0,torch.tensor(prefix))
