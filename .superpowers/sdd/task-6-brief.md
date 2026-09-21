### Task 6: Recalibrar los valores por omisión y contar la verdad

La resolución por omisión (2.0 mm/px) y los `EFFORT_RESTARTS` se calibraron
contra el motor conservador. Con el híbrido, la resolución ya no compra
separación — sólo finura de búsqueda — así que el punto óptimo se corrió. Y
el README promete un objetivo que este plan cambia.

**Files:**
- Modify: `src/nesting/engine/oracle.py` (docstring de `resolution`)
- Modify: `src/nesting/params.py` (`resolucion` por omisión, si la medición lo pide)
- Modify: `docs/superpowers/calibracion.md`
- Modify: `README.md`, `README.es.md`
- Test: `tests/engine/test_effort.py` (los que fijan la calibración)

- [ ] **Step 1: Medir**

Run:
```bash
.venv/bin/python bench/run_bench.py --resoluciones 0.5,1.0,2.0,3.0 --esfuerzos rapido,normal,lento
```
sobre los tres archivos de `bench/files/` más `NESTING 2.ai`. Anotar, por
combinación: placas, material en la última placa, tira sobrante, tiempo,
violaciones.

**Hipótesis a confirmar o refutar, ya medida sobre `NESTING 2.ai`:** con el
motor híbrido, 1 mm/px da el MISMO layout que 2 mm/px y tarda 5x más, porque
la grilla dejó de ser quien define la separación. Si eso se repite en el
bench, `resolucion = 2.0` se queda y hay que reescribir el docstring de
`NestConfig.resolution`, que hoy justifica el valor por un compromiso entre
densidad y tiempo que ya no existe.

- [ ] **Step 2: Fijar los valores por omisión con lo medido**

Actualizar el docstring de `NestConfig.resolution` con la tabla nueva y la
razón del valor elegido, en el mismo estilo que el que está (que cuenta la
medición, no la intuición). Si el óptimo cambió, cambiar
`NestParams.resolucion`.

- [ ] **Step 3: Actualizar los dos README**

La promesa actual es «usar las menos placas posibles y, en la última, dejar
libre la tira más grande posible». Pasa a ser: «usar las menos placas
posibles, dejar la menor cantidad de material posible en la última — que es
lo que acerca a no necesitarla — y, con la misma cantidad, dejarla lo más
compactada posible». Decirlo en los dos idiomas, y agregar que la aplicación
muestra las dos cifras.

- [ ] **Step 4: Run the full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/nesting docs README.md README.es.md tests
git commit -m "Recalibrar con el motor híbrido y contar el objetivo nuevo

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Lo que este plan NO hace

- **No implementa NFP.** Ver el apartado de arriba: es inviable a estos
  conteos de vértices, y el híbrido consigue el mismo resultado (separación
  exacta) por otro camino. Si algún día las piezas vinieran con pocos
  vértices, valdría la pena revisarlo.
- **No agrega búsqueda local sobre posiciones ya elegidas** (recocido,
  "sacudir y reinsertar"). La pasada de recuperación de la tarea 5 es el
  caso barato y de mayor rinde; una búsqueda local de verdad es otro plan, y
  conviene medir primero cuánto queda sobre la mesa después de las tareas
  1 a 5.
- **No toca el lector de archivos ni el escritor de DXF.**

## El techo, para saber cuándo parar

Sobre `NESTING 2.ai`, con separación 10 mm, las 36 piezas infladas 5 mm ocupan
**3.010 m²**, contra **4.670 m²** de área útil: una sola placa exige empaquetar
al **64.4%**. Es una cota dura — en un layout válido esas piezas infladas son
disjuntas — así que ningún algoritmo la baja. Hoy la placa 1 llega a ~52%; con el híbrido más el criterio nuevo, a 53.5%,
con 34 de las 36 piezas arriba. Si después de este plan el motor queda cerca del 64% y sigue
usando dos placas, el problema ya no es el motor.
