"""Generación reproducible del material original; no constituye revisión docente."""
import json
from pathlib import Path
from tutor.reference import solve

PROVENANCE = dict(kind="original_demo", platform="Material propio de demostración",
                  external_id=None, url=None, review_status="Comprobación automática; revisión docente pendiente",
                  license_note="Material original del prototipo. Uso educativo permitido.")
CONCEPTS = [
    ("c-estado", "Estado y simulación", "simulacion", "El estado resume lo que cambia. En cada evento identifica el estado anterior y aplica una sola transición. Ejemplo: una pila con 2 fichas recibe 3 y después pierde 1: los estados son 2, 5, 4. El orden puede importar."),
    ("c-modulo", "Ciclos y módulo", "modulo", "El módulo representa posiciones cíclicas. En un ciclo de 5 posiciones, avanzar 7 desde 1 termina en 3. En C++ el resto de un número negativo puede ser negativo; sumar el tamaño y volver a tomar el resto normaliza la posición."),
    ("c-recorrido", "Recorridos de arreglos", "arreglos", "Un arreglo de n elementos tiene índices C++ de 0 a n-1. Si una salida pide posiciones desde 1, convierte solo al informar. Para comparar vecinos, el índice anterior debe existir. Con n=1 no hay parejas adyacentes."),
    ("c-acumulador", "Acumuladores e invariantes", "acumulacion", "Un acumulador conserva un resultado parcial. Al sumar 3, -2 y 4, los parciales son 0, 3, 1, 5. El invariante describe qué representa tras procesar i elementos. La suma puede requerir long long aunque cada dato quepa en int."),
    ("c-prefijos", "Sumas de prefijos", "prefijos", "Un prefijo almacena la suma desde el principio hasta una frontera. Para [2, 5, -1], los prefijos incluyendo el vacío son [0, 2, 7, 6]. Restar prefijos cancela la parte compartida. Definir las fronteras evita errores de una posición."),
    ("c-lineal", "Búsqueda lineal", "busqueda_lineal", "Una búsqueda lineal examina candidatos y comprueba una condición. Si se pide el primero, importa el orden. Define qué devolver si no hay coincidencia. Buscar en [8, 3, 8] distingue primera posición de número de apariciones."),
    ("c-binaria", "Búsqueda binaria y monotonía", "busqueda_binaria", "Binary search necesita una condición monótona: una zona falsa seguida de una verdadera. En [1, 2, 2, 9], el predicado valor >= 2 es falso, verdadero, verdadero, verdadero. Mantén un intervalo con un invariante claro y comprueba frontera vacía y duplicados. No se aplica a datos arbitrariamente desordenados."),
    ("c-pares", "Enumeración sin duplicados", "enumeracion", "Para enumerar pares de posiciones diferentes sin contar el orden, usa la relación i < j. Tres objetos tienen los pares (0,1), (0,2), (1,2). Valores iguales en posiciones distintas siguen siendo objetos distintos. Estima el número de candidatos antes de elegir el método."),
]

# id, título, tema, dificultad, prerequisitos, conceptos, enunciado, restricciones,
# entrada, salida, explicación, estrategia, error, N1, N2, N3, pruebas, cuerpo C++
ROWS = [
 ("sim-01", "Saldo del depósito", "simulacion", 1, ["variables", "bucles"], ["c-estado", "c-acumulador"],
  "Un depósito comienza con s litros. Se aplican n cambios enteros: positivos añaden agua y negativos la retiran. Informa el volumen final. Se garantiza que ningún estado tiene volumen negativo.",
  "1 <= n <= 100000; 0 <= s <= 10^9; -10^9 <= cambio <= 10^9; cada volumen parcial es no negativo.", "n y s; luego n cambios.", "Volumen final en litros.",
  "El volumen es el estado y cada cambio modifica ese estado.", "Iniciar un acumulador long long con s y sumar cada cambio; O(n), espacio O(1).", "Iniciar en cero y olvidar s; usar int para la suma.",
  "Prueba un depósito con 4 litros que recibe 2 y pierde 1. ¿Qué cambia en cada evento?", "Un acumulador puede comenzar con un valor distinto de cero. Relaciónalo con el volumen inicial.", "Define qué debe contener tu variable justo después de leer un cambio; compruébalo en el primer evento.",
  ["3 4\n2 -1 3\n", "1 0\n0\n", "3 1000000000\n1000000000 1000000000 -1\n"],
  "int n; long long s,x; cin>>n>>s; while(n--){cin>>x;s+=x;} cout<<s<<'\\n';"),
 ("sim-02", "Reloj de saltos", "simulacion", 1, ["variables", "aritmetica"], ["c-modulo"],
  "Un reloj muestra una hora h entre 0 y 23. Cada minuto de una simulación avanza d horas. Calcula la hora después de m minutos; avanzar puede dar varias vueltas.",
  "0 <= h <= 23; 0 <= d <= 10^6; 0 <= m <= 10^9.", "h d m.", "Hora final entre 0 y 23.", "Las horas son un ciclo de longitud 24.", "Calcular (h+d*m)%24 con long long. O(1).", "Olvidar las vueltas; desbordar d*m.",
  "Observa qué muestra el reloj al avanzar desde 23 una hora.", "El resto conserva la posición en un ciclo. Prueba primero con un ciclo de 5 posiciones.", "Antes de multiplicar, decide el tipo de las variables usando el máximo de d*m.",
  ["23 2 2\n", "0 7 0\n", "12 1000000 1000000000\n"],
  "long long h,d,m;cin>>h>>d>>m;cout<<(h+d*m)%24<<'\\n';"),
 ("sim-03", "Robot en la plaza", "simulacion", 2, ["variables", "bucles", "condicionales"], ["c-estado"],
  "Un robot inicia en (0,0). Cada orden lo mueve una unidad: 0 al norte (y aumenta), 1 al este (x aumenta), 2 al sur, 3 al oeste. Informa su posición final.",
  "1 <= n <= 100000; cada orden pertenece a {0,1,2,3}.", "n; luego n órdenes.", "Coordenadas x y finales separadas por espacio.", "El estado contiene dos coordenadas independientes.", "Recorrer órdenes y aplicar desplazamientos (0,1),(1,0),(0,-1),(-1,0); O(n).", "Intercambiar ejes; tratar norte como x positivo.",
  "Dibuja el efecto de una orden norte seguida de una sur.", "Un estado puede tener dos variables. Una orden no necesariamente modifica ambas.", "Construye una tabla para una sola orden y comprueba que el eje que no cambia se conserva.",
  ["4\n0 1 0 3\n", "1\n2\n", "4\n0 1 2 3\n"],
  "int n,d,x=0,y=0;int dx[4]={0,1,0,-1},dy[4]={1,0,-1,0};cin>>n;while(n--){cin>>d;x+=dx[d];y+=dy[d];}cout<<x<<' '<<y<<'\\n';"),
 ("sim-04", "Ventanilla por minutos", "simulacion", 2, ["variables", "bucles", "condicionales"], ["c-estado"],
  "La cola está vacía. En cada minuto primero llegan a_i personas y luego se atiende a una persona si hay alguien esperando. Calcula cuántas quedan tras n minutos.",
  "1 <= n <= 100000; 0 <= a_i <= 100000.", "n; luego n cantidades de llegadas.", "Personas restantes después de la última atención.", "La transición incluye llegada antes que servicio y no permite negativos.", "Actualizar cola=max(0,cola+a_i-1) con long long; O(n).", "Atender antes de las llegadas; hacer negativa la cola.",
  "Compara un minuto con cero llegadas y otro con una llegada partiendo de una cola vacía.", "El orden de dos acciones en una transición importa. La cola nunca puede ser negativa.", "Escribe el estado inmediatamente después de las llegadas, antes de decidir si corresponde atender.",
  ["3\n2 0 3\n", "3\n0 0 0\n", "1\n1\n"],
  "int n;long long q=0,a;cin>>n;while(n--){cin>>a;q=max(0LL,q+a-1);}cout<<q<<'\\n';"),
 ("arr-01", "Balance de mediciones", "arreglos", 1, ["variables", "bucles"], ["c-acumulador"],
  "Se registran n mediciones enteras, que pueden ser negativas. Calcula su suma exacta.",
  "1 <= n <= 100000; -10^9 <= a_i <= 10^9.", "n; luego n mediciones.", "Suma de las mediciones.", "La suma parcial comienza en el elemento neutro cero.", "Sumar en long long durante un recorrido; O(n), O(1).", "Usar int; ignorar números negativos.",
  "Suma a mano [3,-2,4] y anota el valor parcial después de cada elemento.", "Un acumulador guarda el resultado del prefijo procesado; el tipo debe admitir la suma máxima.", "Calcula la cota n*max(abs(a_i)) antes de elegir el tipo de la suma.",
  ["3\n3 -2 4\n", "1\n-7\n", "3\n1000000000 1000000000 1000000000\n"],
  "int n;long long s=0,x;cin>>n;while(n--){cin>>x;s+=x;}cout<<s<<'\\n';"),
 ("arr-02", "Primer pico máximo", "arreglos", 2, ["variables", "bucles", "condicionales"], ["c-recorrido"],
  "Dadas n alturas, informa la posición de la primera aparición de la altura máxima. Las posiciones empiezan en 1.",
  "1 <= n <= 100000; -10^9 <= a_i <= 10^9.", "n; luego n alturas.", "Posición desde 1 del primer máximo.", "Los empates deben conservar la primera posición.", "Inicializar con el primer elemento, actualizar máximo y posición solo con un valor estrictamente mayor; O(n).", "Inicializar máximo en cero con alturas negativas; actualizar en empates.",
  "En [5,5,1], ¿qué posición pide exactamente la palabra primera?", "La condición de actualización decide el tratamiento de empates; compara > con >= en un caso pequeño.", "Comprueba tu inicialización usando un arreglo de un solo elemento negativo.",
  ["5\n-3 7 7 2 1\n", "1\n-8\n", "3\n-5 -2 -2\n"],
  "int n,pos=1;long long best,x;cin>>n>>best;for(int i=2;i<=n;i++){cin>>x;if(x>best){best=x;pos=i;}}cout<<pos<<'\\n';"),
 ("arr-03", "Subidas consecutivas", "arreglos", 2, ["variables", "bucles", "condicionales"], ["c-recorrido"],
  "Cuenta cuántas parejas de días consecutivos tienen una medición estrictamente mayor en el segundo día. No cuentes parejas de días no consecutivos.",
  "1 <= n <= 100000; -10^9 <= a_i <= 10^9.", "n; luego n mediciones diarias.", "Número de subidas entre vecinos.", "Hay n-1 parejas vecinas, y cero si n=1.", "Comparar cada elemento desde el segundo con el anterior; incrementar si es mayor; O(n).", "Contar igualdad como subida; acceder al índice -1.",
  "Marca únicamente las parejas vecinas de [1,3,3,2].", "Para comparar con el anterior, ese anterior debe existir; relaciona esto con la primera iteración.", "Evalúa tu bucle con n=1 y explica cuántas comparaciones debería hacer.",
  ["4\n1 3 3 2\n", "1\n9\n", "5\n-2 -1 0 1 2\n"],
  "int n,ans=0;long long prev,x;cin>>n>>prev;for(int i=1;i<n;i++){cin>>x;ans+=(x>prev);prev=x;}cout<<ans<<'\\n';"),
 ("arr-04", "Consultas de energía", "arreglos", 3, ["arreglos", "acumulacion"], ["c-prefijos", "c-acumulador"],
  "Se conocen n valores diarios de energía, sin modificaciones posteriores. Responde q consultas: suma los valores de los días l a r, incluyendo ambos. Los días se numeran desde 1.",
  "1 <= n,q <= 100000; -10^6 <= a_i <= 10^6; 1 <= l <= r <= n.", "n q; n valores; luego q líneas l r.", "Una suma por línea, en el orden de las consultas.", "Las consultas reutilizan sumas parciales de datos estáticos.", "Construir p[0]=0, p[i]=p[i-1]+a_i. Responder p[r]-p[l-1] en long long; O(n+q).", "Restar p[l] y excluir el primer día; resolver cada consulta recorriendo todo el rango.",
  "Si dos consultas comparten muchos días, observa qué suma estás calculando de nuevo.", "Los prefijos almacenan sumas desde el comienzo; restarlos cancela días comunes.", "Dibuja las fronteras de una consulta de un solo día y comprueba qué parte debe cancelarse.",
  ["4 3\n2 5 -1 3\n1 4\n2 2\n2 3\n", "1 1\n-9\n1 1\n", "3 2\n0 0 0\n1 1\n1 3\n"],
  "int n,q,l,r;cin>>n>>q;vector<long long> p(n+1);for(int i=1;i<=n;i++){cin>>p[i];p[i]+=p[i-1];}while(q--){cin>>l>>r;cout<<p[r]-p[l-1]<<'\\n';}"),
 ("bus-01", "Primera ficha buscada", "busqueda", 1, ["variables", "bucles", "condicionales"], ["c-lineal", "c-recorrido"],
  "Busca un valor x en una lista que no necesariamente está ordenada. Informa la primera posición donde aparece o -1 si no aparece. Las posiciones empiezan en 1.",
  "1 <= n <= 100000; -10^9 <= x,a_i <= 10^9.", "n x; luego n valores.", "Primera posición desde 1, o -1.", "Se necesita la primera coincidencia en el orden original.", "Recorrer manteniendo respuesta -1 y asignar solo en la primera coincidencia; O(n).", "Devolver la última coincidencia; usar búsqueda binaria sin orden.",
  "Prueba buscar 4 en [4,1,4] y luego buscar 7 en esa misma lista.", "Una búsqueda necesita definir tanto éxito como ausencia. El orden original determina la primera coincidencia.", "Revisa qué sucede con tu respuesta cuando ya encontraste una coincidencia y aparece otra.",
  ["3 4\n4 1 4\n", "3 7\n4 1 4\n", "1 -2\n-2\n"],
  "int n,ans=-1;long long x,a;cin>>n>>x;for(int i=1;i<=n;i++){cin>>a;if(a==x&&ans==-1)ans=i;}cout<<ans<<'\\n';"),
 ("bus-02", "Primera talla suficiente", "busqueda", 3, ["arreglos", "busqueda_lineal"], ["c-binaria"],
  "Una lista de tallas está ordenada de menor a mayor, con posibles repeticiones. Encuentra la primera posición cuyo valor sea al menos x. Si no existe, informa -1. Posiciones desde 1.",
  "1 <= n <= 200000; -10^9 <= x,a_i <= 10^9; a_i <= a_(i+1).", "n x; luego n tallas ordenadas.", "Primera posición suficiente desde 1, o -1.", "El predicado a_i >= x es monótono.", "Búsqueda binaria de la frontera inferior en [0,n); si retorna n no existe. O(log n) tras leer O(n).", "Buscar solo igualdad; perder la primera de varias tallas repetidas.",
  "Marca las tallas que cumplen el pedido en [1,2,2,9] para x=2.", "Una condición monótona cambia de falso a verdadero una sola vez; el objetivo puede ser encontrar esa frontera.", "Decide cómo representarás la ausencia de una talla suficiente antes de ajustar los límites.",
  ["4 2\n1 2 2 9\n", "3 10\n1 4 9\n", "1 0\n5\n"],
  "int n;long long x;cin>>n>>x;vector<long long>a(n);for(auto &v:a)cin>>v;auto it=lower_bound(a.begin(),a.end(),x);cout<<(it==a.end()?-1:int(it-a.begin())+1)<<'\\n';"),
 ("bus-03", "Parejas de tarjetas", "busqueda", 2, ["arreglos", "bucles", "condicionales"], ["c-pares"],
  "Cuenta los pares de posiciones distintas i<j cuyas tarjetas sumen t. Dos tarjetas con el mismo valor en posiciones diferentes son distintas. El orden de un par no crea otro par.",
  "1 <= n <= 1000; -10^9 <= t,a_i <= 10^9.", "n t; luego n valores.", "Cantidad de pares de posiciones con suma t.", "Se enumeran pares de índices, no pares de valores únicos.", "Dos bucles con j desde i+1, comprobar suma en long long; O(n^2), aceptable para n<=1000.", "Contar (i,j) y (j,i); emparejar una tarjeta consigo misma; quitar duplicados de valor.",
  "Enumera los pares de posiciones en tres tarjetas iguales sin invertir su orden.", "La relación i<j evita duplicar pares y excluye usar la misma posición dos veces.", "Antes de optimizar, estima cuántas parejas hay con n=1000 y compáralo con tu idea.",
  ["4 4\n2 2 1 3\n", "1 4\n2\n", "3 0\n0 0 0\n"],
  "int n;long long t,ans=0;cin>>n>>t;vector<long long>a(n);for(auto &x:a)cin>>x;for(int i=0;i<n;i++)for(int j=i+1;j<n;j++)ans+=(a[i]+a[j]==t);cout<<ans<<'\\n';"),
 ("bus-04", "Lado para las baldosas", "busqueda", 3, ["aritmetica", "busqueda_lineal"], ["c-binaria"],
  "Necesitas al menos k posiciones en un tablero cuadrado de lado entero positivo d. El tablero tiene d*d posiciones. Encuentra el menor lado posible.",
  "1 <= k <= 10^12.", "Un entero k.", "Menor entero positivo d con d*d >= k.", "La capacidad crece con el lado, así que el predicado suficiente es monótono.", "Buscar el primer d suficiente en [1,1000000] usando long long para d*d; O(log 10^6).", "Redondear mal una raíz flotante; desbordar un producto int.",
  "Compara la capacidad de lados 2 y 3 cuando necesitas 5 posiciones.", "El predicado suficiente pasa de falso a verdadero. Una búsqueda de frontera puede trabajar sobre respuestas posibles.", "Encuentra una cota superior que siempre sea suficiente usando el máximo permitido para k.",
  ["5\n", "1\n", "1000000000000\n", "999999999999\n"],
  "long long k,l=1,r=1000000;cin>>k;while(l<r){long long m=l+(r-l)/2;if(m*m>=k)r=m;else l=m+1;}cout<<l<<'\\n';"),
]

CLARIFICATIONS={
    "sim-01":"s es el volumen inicial; cada cambio se añade o retira después. La salida es el volumen final, no la suma de entradas positivas.",
    "sim-02":"m cuenta minutos de simulación; d indica cuántas horas avanza el reloj en cada minuto. La salida es una hora entre 0 y 23.",
    "sim-03":"Las órdenes 0,1,2,3 representan direcciones, no distancias. Norte cambia y; este cambia x. La salida tiene dos coordenadas.",
    "sim-04":"En cada minuto llegan las personas antes de atender. Se atiende como máximo a una y una cola vacía permanece en cero.",
    "arr-01":"Cada número es una medición, incluso si es negativo. Se solicita una suma total, no una posición ni una cantidad de mediciones.",
    "arr-02":"La respuesta es una posición desde 1, no el valor máximo. Si el máximo se repite, se pide su primera aparición.",
    "arr-03":"Días consecutivos son posiciones vecinas en la secuencia temporal. En [1,3,3,2], las mediciones de los días 1 y 2 son 1 y 3; los valores medidos no son números de día. Una igualdad no es un aumento estricto.",
    "arr-04":"l y r son posiciones de días desde 1; ambos extremos se incluyen. No son valores de energía.",
    "bus-01":"La lista puede estar desordenada. Se pide la primera posición desde 1; -1 representa que el valor no aparece.",
    "bus-02":"Una talla suficiente puede ser igual o mayor que x. La primera se refiere a su posición en la lista ordenada.",
    "bus-03":"Se cuentan pares de posiciones distintas. Dos tarjetas con igual valor siguen siendo dos tarjetas; invertir el orden no forma otro par.",
    "bus-04":"k es la cantidad mínima de posiciones necesarias; d es el lado entero que debes informar, no la capacidad del tablero.",
}


def build():
    problems = []
    for row in ROWS:
        (pid,title,topic,difficulty,prereqs,concepts,statement,constraints,inp,out,explanation,strategy,error,n1,n2,n3,inputs,cpp) = row
        tests = [dict(input=raw, output=solve(pid, raw)) for raw in inputs]
        problems.append(dict(id=pid,title=title,topics=[topic]+[c[2] for c in CONCEPTS if c[0] in concepts],
            prerequisites=prereqs,difficulty=difficulty,difficulty_scale="demo_local_1_5",language="es",programming_language="C++17",
            statement=statement,constraints=constraints,input_format=inp,output_format=out,examples=tests[:1],
            explanation=explanation,reference_strategy=strategy,reference_cpp="#include <bits/stdc++.h>\nusing namespace std;\nint main(){ios::sync_with_stdio(false);cin.tie(nullptr);"+cpp+"}\n",
            common_errors=error.split("; "),tests=tests,
            guidance=[dict(level=i,text=text,step=f"{pid}-focus-{i}") for i,text in enumerate([CLARIFICATIONS[pid],n1,n2,n3])],
            concept_ids=concepts,provenance=PROVENANCE))
    corpus = dict(schema_version=1,problems=problems,concepts=[dict(id=cid,title=title,topics=[topic],text=body,language="es",min_level=2,provenance=PROVENANCE) for cid,title,topic,body in CONCEPTS])
    from tutor.models import Corpus
    Corpus.model_validate(corpus)
    Path("corpus").mkdir(exist_ok=True)
    Path("corpus/demo.json").write_text(json.dumps(corpus,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"Corpus: {len(problems)} problemas originales, {len(CONCEPTS)} conceptos.")


if __name__ == "__main__":
    build()
