#!/usr/bin/env python3
"""
Puente de audio virtual PipeWire para Modo Llamada de TARS.
Crea dispositivos virtuales mediante pactl (module-null-sink) y conecta
flujos PCM 16kHz mono (s16le) usando pacat y parec.
"""

import argparse
import asyncio
import json
import logging
import os
import shutil
import subprocess
import sys
import threading
from typing import AsyncIterator, Dict, Iterator, List, Optional, Tuple, Union

logger = logging.getLogger("tars.voice_bridge")


class PipeWireVoiceBridge:
    """Gestiona nodos virtuales PipeWire y streaming PCM 16kHz mono bidireccional."""

    MIC_SINK_NAME = "TARS_Phone_Mic_Sink"
    MIC_SOURCE_NAME = "TARS_Phone_Mic_Sink.monitor"
    SPEAKER_SINK_NAME = "TARS_Antigravity_Out"
    SPEAKER_MONITOR_NAME = "TARS_Antigravity_Out.monitor"

    BRIDGE_MIC_CLIENT = "TARS_Voice_Bridge_Mic"
    BRIDGE_SPEAKER_CLIENT = "TARS_Voice_Bridge_Speaker"

    DEFAULT_SAMPLE_RATE = 16000
    DEFAULT_CHANNELS = 1
    DEFAULT_SAMPLE_FORMAT = "s16le"
    DEFAULT_CHUNK_BYTES = 1280  # 40 ms a 16kHz, 16-bit mono (32000 bytes/s)
    DEFAULT_LATENCY_MSEC = 40

    TARGET_APP_KEYWORDS = ("antigravity", "electron", "chromium")
    EXCLUDED_BINARIES = ("pacat", "parec", "qtwebengineprocess")
    EXCLUDED_CLIENTS = (BRIDGE_MIC_CLIENT.lower(), BRIDGE_SPEAKER_CLIENT.lower())

    def __init__(
        self,
        mic_sink_name: str = MIC_SINK_NAME,
        speaker_sink_name: str = SPEAKER_SINK_NAME,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        channels: int = DEFAULT_CHANNELS,
        sample_format: str = DEFAULT_SAMPLE_FORMAT,
        chunk_bytes: int = DEFAULT_CHUNK_BYTES,
        latency_msec: int = DEFAULT_LATENCY_MSEC,
    ) -> None:
        self.mic_sink_name = mic_sink_name
        self.mic_source_name = f"{mic_sink_name}.monitor"
        self.speaker_sink_name = speaker_sink_name
        self.speaker_monitor_name = f"{speaker_sink_name}.monitor"
        self.sample_rate = int(sample_rate)
        self.channels = int(channels)
        self.sample_format = sample_format
        self.chunk_bytes = int(chunk_bytes)
        self.latency_msec = int(latency_msec)

        self._lock = threading.RLock()
        self._active = False
        self._module_ids: List[int] = []
        self._saved_sink_inputs: Dict[int, Union[int, str]] = {}
        self._saved_source_outputs: Dict[int, Union[int, str]] = {}
        self._pacat_proc: Optional[subprocess.Popen] = None
        self._parec_proc: Optional[subprocess.Popen] = None
        self._env = dict(os.environ, LC_ALL="C")

    def __enter__(self) -> "PipeWireVoiceBridge":
        self.setup()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.teardown()

    @property
    def is_active(self) -> bool:
        return self._active

    def _require_tools(self) -> None:
        missing = [tool for tool in ("pactl", "pacat", "parec") if not shutil.which(tool)]
        if missing:
            raise RuntimeError(f"Herramientas de audio faltantes en PATH: {', '.join(missing)}")

    def _run_pactl(self, args: List[str], check: bool = True) -> subprocess.CompletedProcess:
        cmd = ["pactl", *args]
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=self._env,
            check=check,
        )

    def _pactl_json(self, args: List[str]):
        res = self._run_pactl(["-f", "json", *args], check=True)
        raw = (res.stdout or "").strip()
        if not raw:
            return []
        return json.loads(raw)

    def _cleanup_stale_virtual_sinks(self) -> None:
        """Descarga modulos residuales de sesiones previas que usen los mismos nombres de sink."""
        try:
            sinks = self._pactl_json(["list", "sinks"])
        except Exception as exc:
            logger.debug("No se pudo inspeccionar sinks previos: %s", exc)
            return

        target_names = {self.mic_sink_name, self.speaker_sink_name}
        seen_modules = set()
        for sink in sinks:
            if sink.get("name") in target_names:
                owner_mod = sink.get("owner_module")
                if owner_mod is not None:
                    try:
                        mod_id = int(owner_mod)
                    except (TypeError, ValueError):
                        continue
                    if mod_id not in seen_modules:
                        seen_modules.add(mod_id)
                        logger.info("Limpiando modulo virtual previo %s (%s)", mod_id, sink.get("name"))
                        self._run_pactl(["unload-module", str(mod_id)], check=False)

    def _load_null_sink(self, sink_name: str) -> int:
        args = [
            "load-module",
            "module-null-sink",
            f"sink_name={sink_name}",
            f"sink_properties=device.description={sink_name}",
            f"format={self.sample_format}",
            f"rate={self.sample_rate}",
            f"channels={self.channels}",
        ]
        res = self._run_pactl(args, check=True)
        module_str = (res.stdout or "").strip()
        try:
            module_id = int(module_str)
        except ValueError as exc:
            raise RuntimeError(f"Respuesta invalida al cargar module-null-sink ({sink_name}): {module_str!r}") from exc
        self._module_ids.append(module_id)

        # Asegurar que el sink virtual este habilitado y a volumen nominal.
        self._run_pactl(["set-sink-mute", sink_name, "0"], check=False)
        self._run_pactl(["set-sink-volume", sink_name, "100%"], check=False)
        return module_id

    def setup(self) -> Dict[str, Union[int, str]]:
        """Crea TARS_Phone_Mic_Sink (con su monitor como microfono virtual) y TARS_Antigravity_Out."""
        with self._lock:
            self._require_tools()
            if self._active:
                self.teardown()

            self._cleanup_stale_virtual_sinks()
            self._module_ids.clear()
            self._saved_sink_inputs.clear()
            self._saved_source_outputs.clear()

            try:
                mic_mod_id = self._load_null_sink(self.mic_sink_name)
                speaker_mod_id = self._load_null_sink(self.speaker_sink_name)
                self._active = True
                logger.info(
                    "Nodos PipeWire creados: %s (mod %d), %s (mod %d)",
                    self.mic_sink_name,
                    mic_mod_id,
                    self.speaker_sink_name,
                    speaker_mod_id,
                )
                return {
                    "mic_sink": self.mic_sink_name,
                    "mic_source": self.mic_source_name,
                    "mic_module_id": mic_mod_id,
                    "speaker_sink": self.speaker_sink_name,
                    "speaker_monitor": self.speaker_monitor_name,
                    "speaker_module_id": speaker_mod_id,
                }
            except Exception:
                self.teardown()
                raise

    def _build_client_map(self) -> Dict[str, Dict]:
        clients = self._pactl_json(["list", "clients"])
        client_map: Dict[str, Dict] = {}
        for client in clients:
            idx = client.get("index")
            if idx is not None:
                client_map[str(idx)] = client.get("properties") or {}
        return client_map

    def _matches_antigravity(self, stream: Dict, client_map: Dict[str, Dict]) -> bool:
        stream_props = stream.get("properties") or {}
        client_id = stream.get("client")
        client_props = client_map.get(str(client_id), {}) if client_id is not None else {}

        app_name = str(
            stream_props.get("application.name")
            or client_props.get("application.name")
            or ""
        ).lower()
        proc_binary = str(
            stream_props.get("application.process.binary")
            or client_props.get("application.process.binary")
            or ""
        ).lower()
        node_name = str(
            stream_props.get("node.name")
            or client_props.get("node.name")
            or ""
        ).lower()
        media_name = str(stream_props.get("media.name") or "").lower()

        # Excluir nuestros propios procesos puente y procesos ajenos conocidos.
        if any(excl in app_name for excl in self.EXCLUDED_CLIENTS):
            return False
        if any(excl in proc_binary for excl in self.EXCLUDED_BINARIES):
            return False

        # Coincidencia directa con Antigravity o Electron.
        for kw in ("antigravity", "electron"):
            if kw in app_name or kw in proc_binary or kw in node_name or kw in media_name:
                return True

        # Chromium (por ejemplo renderer/audio service de Electron cuando se identifica como Chromium).
        if "chromium" in proc_binary or "chromium" in node_name:
            return True
        if "chromium" in app_name and "qtwebengine" not in proc_binary:
            return True

        return False

    def _resolve_sink_index_map(self) -> Dict[str, int]:
        sinks = self._pactl_json(["list", "short", "sinks"])
        return {str(s.get("name")): int(s["index"]) for s in sinks if "name" in s and "index" in s}

    def _resolve_source_index_map(self) -> Dict[str, int]:
        sources = self._pactl_json(["list", "short", "sources"])
        return {str(s.get("name")): int(s["index"]) for s in sources if "name" in s and "index" in s}

    def route_antigravity_audio(self) -> Dict[str, List[int]]:
        """Detecta sink-inputs y source-outputs de Antigravity/Electron/Chromium y los mueve a los nodos virtuales."""
        with self._lock:
            if not self._active:
                raise RuntimeError("PipeWireVoiceBridge no esta inicializado; llama a setup() primero.")

            client_map = self._build_client_map()
            sink_indices = self._resolve_sink_index_map()
            source_indices = self._resolve_source_index_map()

            target_speaker_idx = sink_indices.get(self.speaker_sink_name)
            target_mic_sink_idx = sink_indices.get(self.mic_sink_name)
            target_mic_source_idx = source_indices.get(self.mic_source_name)

            moved_sink_inputs: List[int] = []
            moved_source_outputs: List[int] = []

            for sink_input in self._pactl_json(["list", "sink-inputs"]):
                idx = sink_input.get("index")
                if idx is None:
                    continue
                idx = int(idx)
                current_sink = sink_input.get("sink")
                if current_sink in (target_speaker_idx, target_mic_sink_idx):
                    continue
                if not self._matches_antigravity(sink_input, client_map):
                    continue

                if idx not in self._saved_sink_inputs and current_sink is not None:
                    self._saved_sink_inputs[idx] = current_sink
                try:
                    self._run_pactl(["move-sink-input", str(idx), self.speaker_sink_name], check=True)
                    moved_sink_inputs.append(idx)
                    logger.info("sink-input %d movido a %s", idx, self.speaker_sink_name)
                except subprocess.CalledProcessError as exc:
                    logger.warning("No se pudo mover sink-input %d: %s", idx, exc.stderr.strip())

            for source_output in self._pactl_json(["list", "source-outputs"]):
                idx = source_output.get("index")
                if idx is None:
                    continue
                idx = int(idx)
                current_source = source_output.get("source")
                if current_source == target_mic_source_idx:
                    continue
                if not self._matches_antigravity(source_output, client_map):
                    continue

                if idx not in self._saved_source_outputs and current_source is not None:
                    self._saved_source_outputs[idx] = current_source
                try:
                    self._run_pactl(["move-source-output", str(idx), self.mic_source_name], check=True)
                    moved_source_outputs.append(idx)
                    logger.info("source-output %d movido a %s", idx, self.mic_source_name)
                except subprocess.CalledProcessError as exc:
                    logger.warning("No se pudo mover source-output %d: %s", idx, exc.stderr.strip())

            return {
                "moved_sink_inputs": moved_sink_inputs,
                "moved_source_outputs": moved_source_outputs,
            }

    def _start_pacat(self) -> subprocess.Popen:
        cmd = [
            "pacat",
            "-p",
            "-d",
            self.mic_sink_name,
            "--raw",
            f"--format={self.sample_format}",
            f"--rate={self.sample_rate}",
            f"--channels={self.channels}",
            f"--latency-msec={self.latency_msec}",
            f"--client-name={self.BRIDGE_MIC_CLIENT}",
            "--stream-name=TARS_Phone_Mic_In",
        ]
        return subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            env=self._env,
        )

    def _ensure_pacat(self) -> subprocess.Popen:
        if self._pacat_proc is None or self._pacat_proc.poll() is not None:
            self._terminate_process(self._pacat_proc)
            self._pacat_proc = self._start_pacat()
        return self._pacat_proc

    def write_mic_chunk(self, pcm_bytes: bytes) -> bool:
        """Escribe audio PCM 16kHz mono hacia el microfono virtual (TARS_Phone_Mic_Sink)."""
        if not pcm_bytes:
            return True
        with self._lock:
            if not self._active:
                return False
            for attempt in range(2):
                proc = self._ensure_pacat()
                if proc.stdin is None:
                    return False
                try:
                    proc.stdin.write(pcm_bytes)
                    proc.stdin.flush()
                    return True
                except (BrokenPipeError, OSError) as exc:
                    logger.warning("Error escribiendo chunk en pacat (intento %d): %s", attempt + 1, exc)
                    self._terminate_process(self._pacat_proc)
                    self._pacat_proc = None
                    if not self._active:
                        return False
            return False

    def _build_parec_cmd(self) -> List[str]:
        return [
            "parec",
            "-d",
            self.speaker_monitor_name,
            "--raw",
            f"--format={self.sample_format}",
            f"--rate={self.sample_rate}",
            f"--channels={self.channels}",
            f"--latency-msec={self.latency_msec}",
            f"--client-name={self.BRIDGE_SPEAKER_CLIENT}",
            "--stream-name=TARS_Antigravity_Out_Capture",
        ]

    def read_speaker_stream(self, chunk_bytes: Optional[int] = None) -> Iterator[bytes]:
        """Generador que lee chunks PCM 16kHz mono desde TARS_Antigravity_Out.monitor."""
        if not self._active:
            raise RuntimeError("PipeWireVoiceBridge no esta inicializado; llama a setup() primero.")

        read_size = int(chunk_bytes or self.chunk_bytes)
        proc = subprocess.Popen(
            self._build_parec_cmd(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=self._env,
        )
        with self._lock:
            self._terminate_process(self._parec_proc)
            self._parec_proc = proc

        try:
            stdout = proc.stdout
            if stdout is None:
                return
            while self._active:
                data = stdout.read(read_size)
                if not data:
                    break
                yield data
        finally:
            with self._lock:
                if self._parec_proc is proc:
                    self._parec_proc = None
            self._terminate_process(proc)

    async def iter_speaker_stream(self, chunk_bytes: Optional[int] = None) -> AsyncIterator[bytes]:
        """Generador asincrono de chunks PCM 16kHz mono desde TARS_Antigravity_Out.monitor."""
        if not self._active:
            raise RuntimeError("PipeWireVoiceBridge no esta inicializado; llama a setup() primero.")

        read_size = int(chunk_bytes or self.chunk_bytes)
        proc = await asyncio.create_subprocess_exec(
            *self._build_parec_cmd(),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=self._env,
        )
        try:
            assert proc.stdout is not None
            while self._active:
                data = await proc.stdout.read(read_size)
                if not data:
                    break
                yield data
        finally:
            if proc.returncode is None:
                try:
                    proc.terminate()
                except ProcessLookupError:
                    pass
                try:
                    await asyncio.wait_for(proc.wait(), timeout=1.0)
                except asyncio.TimeoutError:
                    try:
                        proc.kill()
                        await proc.wait()
                    except ProcessLookupError:
                        pass

    @staticmethod
    def _terminate_process(proc: Optional[subprocess.Popen]) -> None:
        if proc is None:
            return
        for stream in (proc.stdin, proc.stdout, proc.stderr):
            if stream is not None:
                try:
                    stream.close()
                except Exception:
                    pass
        if proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                try:
                    proc.kill()
                    proc.wait(timeout=1.0)
                except Exception:
                    pass
            except Exception:
                pass

    def _restore_streams(self) -> None:
        if not self._saved_sink_inputs and not self._saved_source_outputs:
            return

        try:
            active_sink_inputs = {
                int(item["index"])
                for item in self._pactl_json(["list", "short", "sink-inputs"])
                if "index" in item
            }
        except Exception:
            active_sink_inputs = set(self._saved_sink_inputs.keys())

        try:
            active_source_outputs = {
                int(item["index"])
                for item in self._pactl_json(["list", "short", "source-outputs"])
                if "index" in item
            }
        except Exception:
            active_source_outputs = set(self._saved_source_outputs.keys())

        try:
            available_sinks = {
                int(item["index"])
                for item in self._pactl_json(["list", "short", "sinks"])
                if "index" in item
            }
        except Exception:
            available_sinks = set()

        try:
            available_sources = {
                int(item["index"])
                for item in self._pactl_json(["list", "short", "sources"])
                if "index" in item
            }
        except Exception:
            available_sources = set()

        for idx, orig_sink in list(self._saved_sink_inputs.items()):
            if idx not in active_sink_inputs:
                continue
            target = str(orig_sink)
            if isinstance(orig_sink, int) and available_sinks and orig_sink not in available_sinks:
                target = "@DEFAULT_SINK@"
            res = self._run_pactl(["move-sink-input", str(idx), target], check=False)
            if res.returncode != 0 and target != "@DEFAULT_SINK@":
                self._run_pactl(["move-sink-input", str(idx), "@DEFAULT_SINK@"], check=False)

        for idx, orig_source in list(self._saved_source_outputs.items()):
            if idx not in active_source_outputs:
                continue
            target = str(orig_source)
            if isinstance(orig_source, int) and available_sources and orig_source not in available_sources:
                target = "@DEFAULT_SOURCE@"
            res = self._run_pactl(["move-source-output", str(idx), target], check=False)
            if res.returncode != 0 and target != "@DEFAULT_SOURCE@":
                self._run_pactl(["move-source-output", str(idx), "@DEFAULT_SOURCE@"], check=False)

        self._saved_sink_inputs.clear()
        self._saved_source_outputs.clear()

    def teardown(self) -> None:
        """Restaura streams movidos, cierra procesos de audio y destruye modulos virtuales."""
        with self._lock:
            self._active = False

            try:
                self._terminate_process(self._pacat_proc)
            finally:
                self._pacat_proc = None

            try:
                self._terminate_process(self._parec_proc)
            finally:
                self._parec_proc = None

            try:
                self._restore_streams()
            except Exception as exc:
                logger.warning("Error restaurando streams en teardown: %s", exc)

            for mod_id in reversed(self._module_ids):
                try:
                    self._run_pactl(["unload-module", str(mod_id)], check=False)
                except Exception as exc:
                    logger.warning("Error descargando modulo %s: %s", mod_id, exc)
            self._module_ids.clear()

            # Respaldo por si algun modulo quedo huerfano.
            self._cleanup_stale_virtual_sinks()


def _run_smoke_test() -> int:
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    bridge = PipeWireVoiceBridge()
    env = dict(os.environ, LC_ALL="C")

    try:
        info = bridge.setup()
        print("Nodos creados:", json.dumps(info))

        sinks_res = subprocess.run(
            ["pactl", "list", "short", "sinks"],
            capture_output=True,
            text=True,
            env=env,
            check=True,
        )
        print("Salida de `pactl list short sinks` con nodos activos:")
        print(sinks_res.stdout.strip())

        has_mic = bridge.mic_sink_name in sinks_res.stdout
        has_speaker = bridge.speaker_sink_name in sinks_res.stdout
        if not (has_mic and has_speaker):
            print(
                f"ERROR: faltan sinks esperados (mic={has_mic}, speaker={has_speaker})",
                file=sys.stderr,
            )
            return 1

        route_info = bridge.route_antigravity_audio()
        print("Resultado de route_antigravity_audio():", json.dumps(route_info))

        # Smoke test rapido de escritura PCM silencio (40ms) hacia el microfono virtual.
        silence = b"\x00" * bridge.chunk_bytes
        wrote = bridge.write_mic_chunk(silence)
        print(f"write_mic_chunk(silence): {wrote}")
        if not wrote:
            print("ERROR: write_mic_chunk fallo", file=sys.stderr)
            return 1
    finally:
        bridge.teardown()

    after_res = subprocess.run(
        ["pactl", "list", "short", "sinks"],
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )
    print("Salida de `pactl list short sinks` tras teardown:")
    print(after_res.stdout.strip())
    if bridge.mic_sink_name in after_res.stdout or bridge.speaker_sink_name in after_res.stdout:
        print("ERROR: quedaron sinks virtuales sin limpiar tras teardown", file=sys.stderr)
        return 1

    print("OK: verificacion PipeWireVoiceBridge completada y limpia.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Puente de audio PipeWire para Modo Llamada de TARS")
    parser.add_argument(
        "--test",
        action="store_true",
        help="Crea los nodos virtuales, verifica con pactl list short sinks y limpia al salir.",
    )
    args = parser.parse_args()
    if args.test:
        return _run_smoke_test()
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
