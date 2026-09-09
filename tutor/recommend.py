def recommend(catalog, store, student_id, goal=None, max_difficulty=3, limit=3):
    profile = store.profile(student_id)
    observed = profile["observations"]
    known = set(profile["declared_basics"]) | {o["concept"] for o in observed if o["kind"] == "demostracion" and o["status"] == "confirmado"}
    difficulties = {o["concept"] for o in observed if o["kind"] == "dificultad"}
    worked = {s["problem_id"] for s in store.sessions(student_id)}
    candidates = []
    for p in catalog.problems():
        # No comparar escalas de plataformas diferentes con la dificultad local.
        if p.id in worked or p.difficulty_scale != "demo_local_1_5" or p.difficulty > max_difficulty or not set(p.prerequisites) <= known:
            continue
        overlap = set(p.topics)&difficulties
        relevant = goal is None or goal in p.topics
        prepares = goal is not None and any(goal in target.topics and set(p.topics)&set(target.prerequisites) for target in catalog.problems())
        if goal is not None and not relevant and not prepares:
            continue
        reason = ("Reforzar una dificultad observada en "+", ".join(sorted(overlap))) if overlap else (
            "Practicar "+goal+" con otra presentación" if goal and relevant else "Preparar un prerrequisito para "+goal if goal else "Practicar "+p.topics[0]+" con los conocimientos declarados")
        candidates.append((-(3*bool(overlap)+2*bool(goal and relevant)),p.difficulty,p.id,dict(problem=p.public().model_dump(),reason=reason)))
    items = [row[-1] for row in sorted(candidates,key=lambda r:r[:3])[:limit]]
    return dict(items=items,message="Ejercicios adecuados al perfil y al historial." if items else "No hay un ejercicio adecuado en el catálogo para ese objetivo y esos prerrequisitos.")
