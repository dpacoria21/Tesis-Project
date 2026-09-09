"""Oráculos del corpus propio. Nunca se usan para ejecutar código del estudiante."""
from bisect import bisect_left


def solve(problem_id: str, raw: str) -> str:
    v = list(map(int, raw.split()))
    if problem_id == "sim-01":
        n, capacity, *changes = v
        answer = str(capacity + sum(changes[:n]))
    elif problem_id == "sim-02":
        start, delta, minutes = v
        answer = str((start + delta * minutes) % 24)
    elif problem_id == "sim-03":
        n, *commands = v
        x = y = 0
        for d in commands[:n]:
            dx, dy = [(0, 1), (1, 0), (0, -1), (-1, 0)][d]
            x += dx
            y += dy
        answer = f"{x} {y}"
    elif problem_id == "sim-04":
        n, *arrivals = v
        waiting = 0
        for a in arrivals[:n]:
            waiting = max(0, waiting + a - 1)
        answer = str(waiting)
    elif problem_id == "arr-01":
        n, *a = v
        answer = str(sum(a[:n]))
    elif problem_id == "arr-02":
        n, *a = v
        answer = str(a[:n].index(max(a[:n])) + 1)
    elif problem_id == "arr-03":
        n, *a = v
        answer = str(sum(a[i] > a[i - 1] for i in range(1, n)))
    elif problem_id == "arr-04":
        n, q = v[:2]
        a, queries = v[2:2+n], v[2+n:]
        answer = "\n".join(str(sum(a[queries[2*i]-1:queries[2*i+1]])) for i in range(q))
    elif problem_id == "bus-01":
        n, target, *a = v
        answer = str(next((i + 1 for i, x in enumerate(a[:n]) if x == target), -1))
    elif problem_id == "bus-02":
        n, target, *a = v
        i = bisect_left(a[:n], target)
        answer = str(i + 1 if i < n else -1)
    elif problem_id == "bus-03":
        n, target, *a = v
        answer = str(sum(a[i] + a[j] == target for i in range(n) for j in range(i+1, n)))
    elif problem_id == "bus-04":
        target = v[0]
        import math
        d = math.isqrt(target)
        answer = str(d if d*d == target else d+1)
    else:
        raise ValueError("No hay oráculo propio para este identificador.")
    return answer + "\n"
