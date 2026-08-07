# Sin & Punishment: Recompiled

Port nativo a PC de **Sin & Punishment** (N64, Japón 2000, Treasure) mediante
recompilación estática con [N64Recomp](https://github.com/N64Recomp/N64Recomp) y
renderizado con [RT64](https://github.com/rt64/rt64): resolución nativa arbitraria,
widescreen real, alto framerate, controles modernos.

**Estado: preparación.** La repo está scaffolded y el toolchain en verificación.
La implementación se orquesta con subagentes siguiendo [`GOAL.md`](GOAL.md) (fases 0–5).
**No se declara jugable hasta cumplir los criterios de aceptación de la Fase 5.**

## Estructura

```
sinpunishment.toml         Config del recompilador (N64Recomp) — en la raíz, paths relativos
symbols/                    Símbolos del juego (generados por RE con Ghidra, Fase 1)
scripts/                    bootstrap.sh (deps+toolchain), recompile.sh, rom_info.py
rom/sinpunishment.z64       ROM convertida a z64 (gitignored; no commitear)
RecompiledFuncs/            Salida del recompilador (generado, gitignored)
rsp/                        Configs y salida de los microcódigos RSP (ucode GFX F3DEX + audio custom)
src/main, src/game          Código del port (Fases 2–3)
lib/                        Submodulos: N64ModernRuntime, rt64, RecompFrontend
external/N64Recomp          Submodulo: herramientas de recompilación
docs/research.md            Registro del reverse engineering (fuente de verdad)
GOAL.md                     El plan de implementación / goal prompt
```

## Requisitos

- CMake ≥ 3.20, clang, ninja, SDL2 (macOS/Linux). Windows: VS2022 + clang.
- ROM del juego (JP): `rom/sinpunishment.z64` (md5 `a0657bc99e169153fd46aeccfde748f3`).

## Build

```bash
./scripts/bootstrap.sh        # deps + submodulos + herramientas N64Recomp
./scripts/recompile.sh        # genera RecompiledFuncs/ y rsp/*.cpp (requiere symbols/)
cmake -B build -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build build
```

## Hechos clave del juego (detalle en docs/research.md)

- ROM 32 MB, V64 → z64; entrypoint `0x80025C00`; boot libultra estándar.
- Microcódigo GFX: **F3DEX v1** (fifo 2.08). Microcódigo de audio: **custom**.
- Sin decomp público → los símbolos se generan por RE (Fase 1, Ghidra headless).

## Licencia

Este repositorio no contiene assets del juego. El port (código propio) es GPL-3.0,
igual que los proyectos recomp de referencia (Zelda64Recomp, BanjoRecomp).
Submodulos: N64Recomp MIT, RT64 MIT, N64ModernRuntime GPL-3.0, RecompFrontend GPL-3.0.
