"""Puente pequeño al núcleo de LM Format Enforcer para Transformers 5.

La integración upstream 0.11.3 importa PreTrainedTokenizerBase desde una ruta retirada
en Transformers 5; usamos directamente la API del núcleo, sin modificar dependencias.
"""
from lmformatenforcer import JsonSchemaParser, TokenEnforcer, TokenEnforcerTokenizerData


def tokenizer_data(tokenizer):
    specials=set(tokenizer.all_special_ids)
    anchor=tokenizer.encode("0",add_special_tokens=False)[0]
    pieces=[]
    for token_id in range(len(tokenizer)):
        if token_id in specials:
            continue
        isolated=tokenizer.decode([token_id],clean_up_tokenization_spaces=False)
        attached=tokenizer.decode([anchor,token_id],clean_up_tokenization_spaces=False)[1:]
        pieces.append((token_id,attached,len(attached)>len(isolated)))
    def decode(ids):
        return tokenizer.decode(ids,clean_up_tokenization_spaces=False).rstrip("\ufffd")
    return TokenEnforcerTokenizerData(pieces,decode,tokenizer.eos_token_id,False,len(tokenizer))


def prefix_constraint(data,schema):
    enforcer=TokenEnforcer(data,JsonSchemaParser(schema))
    def allowed(batch_id,sequence):
        return enforcer.get_allowed_tokens(sequence.tolist()).allowed_tokens
    return allowed
