"""The existing Qwen assistant-only ChatML encoding, reusable without training."""


def encode_chatml(tokenizer, prompt, target, max_length):
    prefix = tokenizer.apply_chat_template(prompt, tokenize=True, add_generation_prompt=True,
                                          enable_thinking=False, return_dict=False)
    answer = tokenizer.encode(target+'<|im_end|>', add_special_tokens=False)
    ids, labels = prefix+answer, [-100]*len(prefix)+answer
    if len(ids) > max_length:
        raise ValueError(f'Overlength: {len(ids)} > {max_length}; no truncation')
    if not answer:
        raise ValueError('Empty assistant target')
    return {'input_ids': ids, 'labels': labels, 'attention_mask': [1]*len(ids),
            'prompt_tokens': len(prefix), 'target_tokens': len(answer)}
