"""Comprobaciones acotadas de ejemplos numéricos; nunca ejecuta código del estudiante."""
import re


def check_array_examples(problem_id,texts,include_alternative=False):
    if problem_id not in {"arr-01","arr-02","arr-03"}:
        return []
    results=[]
    seen=set()
    for text in texts:
        for match in re.finditer(r"\[\s*-?\d+(?:\s*,\s*-?\d+){0,15}\s*\]",text):
            numbers=tuple(map(int,re.findall(r"-?\d+",match.group())))
            if numbers in seen or any(abs(n)>10**9 for n in numbers):
                continue
            seen.add(numbers)
            fact=dict(values=list(numbers),origin="Cálculo determinista del ejemplo textual; no ejecución de código")
            if problem_id=="arr-01": fact["sum"]=sum(numbers)
            elif problem_id=="arr-02":
                maximum=max(numbers)
                fact["first_max_position"]=numbers.index(maximum)+1
                if include_alternative:
                    fact["update_on_equal_position"]=len(numbers)-numbers[::-1].index(maximum)
            else:
                fact.update(adjacent_pairs=list(zip(numbers,numbers[1:])),pair_count=len(numbers)-1,
                            strict_increases=sum(b>a for a,b in zip(numbers,numbers[1:])))
            results.append(fact)
    return results


def check_tie_update_claims(problem_id,message,student_content):
    """Contrasta una afirmación explícita de la salida de >= en un único arreglo.

    Solo interpreta una afirmación positiva atribuida a la regla del alumno.
    Preguntas, negaciones, citas, condiciones y sujetos distintos se dejan al
    revisor semántico; la mera aparición de una posición no es una afirmación.
    """
    if problem_id != "arr-02" or not re.search(r"mayor o igual|igual o m[aá]s grande|>=",student_content,re.I):
        return []
    facts=check_array_examples(problem_id,[message],include_alternative=True)
    if len(facts)!=1:
        return []
    ordinal={"primera":1,"segunda":2,"tercera":3,"cuarta":4}
    claim_pattern=re.compile(
        r"\btu\s+(?:regla|c[oó]digo|m[eé]todo|algoritmo|condici[oó]n|propuesta)\s+"
        r"(?:actual\s+)?(?:devolver[ií]a|elegir[ií]a|seleccionar[ií]a|conservar[ií]a|guardar[ií]a)\s+"
        r"(?:la\s+)?(?:posici[oó]n\s+)?(?P<position>\d+|primera|segunda|tercera|cuarta)\b",
        re.I,
    )
    for sentence in re.split(r"(?<=[.!?;])\s+|\n",message):
        if re.search(r'[¿?«»"“”]|\b(?:no|nunca|jam[aá]s|ni|si|quiz[aá]s|tal vez)\b',sentence,re.I):
            continue
        for claim in claim_pattern.finditer(sentence):
            # Un método corregido/hipotético adicional no es necesariamente la
            # propuesta >= que estamos comprobando.
            if re.search(r"\b(?:correg|corrig|modific|cambi|sustituy|reemplaz)\w*",sentence,re.I):
                continue
            value=claim.group("position").lower()
            actual=int(value) if value.isdigit() else ordinal[value]
            if actual!=facts[0]["update_on_equal_position"]:
                return [f"En el arreglo del ejemplo, actualizar también con igualdad conserva la posición {facts[0]['update_on_equal_position']} (desde 1). El resultado atribuido a esa regla es incorrecto; usa el ejemplo comprobado sin invertir las posiciones."]
    return []


def check_pair_claims(problem_id,message):
    """Detecta contradicciones concretas en enumeraciones que se presentan como exhaustivas."""
    if problem_id!="arr-03": return []
    facts=check_array_examples(problem_id,[message])
    pairs=[tuple(map(int,m)) for m in re.findall(r"\(\s*(-?\d+)\s*,\s*(-?\d+)\s*\)",message)]
    if len(facts)!=1 or not pairs: return []
    valid=facts[0]["adjacent_pairs"]
    if any(pair not in valid for pair in pairs):
        return ["Una pareja presentada no es vecina en el arreglo del ejemplo."]
    from collections import Counter
    if len(pairs)>=2 and re.search(r"\b(solo|únicamente|solamente)\b",message,re.I) and Counter(pairs)!=Counter(valid):
        return ["La enumeración presentada como exclusiva omite o duplica parejas vecinas del ejemplo; revisar también valores iguales."]
    return []


def check_prefix_interval_claims(problem_id,message):
    """Verifica un resultado numérico de intervalo cuando el texto explicita sus prefijos.

    No interpreta código, expresiones arbitrarias ni ejemplos sin fronteras numéricas.
    """
    if problem_id!="arr-04": return []
    prefix=re.search(r"prefijos[^\[\]\n]{0,80}\[\s*(0(?:\s*,\s*-?\d+){1,16})\s*\]",message,re.I)
    if not prefix: return []
    values=list(map(int,re.findall(r"-?\d+",prefix.group(1))))
    if any(abs(n)>10**12 for n in values): return []
    for claim in re.finditer(r"suma\s+(?:de\s+)?(?:los\s+)?d[ií]as\s+(\d+)\s+a\s+(\d+)\s+es\s+([^.!?\n]+)",message,re.I):
        left,right=map(int,claim.group(1,2))
        expression=claim.group(3).strip()
        if not re.fullmatch(r"[-\d\s+=]+",expression): continue
        result=re.search(r"(?:^|=)\s*(-?\d+)\s*$",expression)
        if result and 1<=left<=right<len(values) and int(result.group(1))!=values[right]-values[left-1]:
            return ["El resultado numérico del intervalo no corresponde a las fronteras de los prefijos que aparecen en el ejemplo. Revisa los índices antes de responder."]
    return []
