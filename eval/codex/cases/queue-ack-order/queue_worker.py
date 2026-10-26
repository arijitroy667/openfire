def process(payload, persist, acknowledge):
    acknowledge(payload)
    return persist(payload)
