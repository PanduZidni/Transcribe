import os
import sys
import tempfile
import threading
import argparse
import shutil
import traceback
import math   # NEW
import subprocess  # NEW
import io

# Matikan tqdm dan siapkan "dummy" stdout/stderr agar tidak None di mode GUI
os.environ.setdefault("TQDM_DISABLE", "1")
if sys.stderr is None: sys.stderr = io.StringIO()
if sys.stdout is None: sys.stdout = io.StringIO()

# ==== ensure ffmpeg is reachable at runtime1 (portable / winget / manual) ====
def _wire_ffmpeg_runtime():
    try:
        # 0) If user specifies FFMPEG_BINARY explicitly, honor it
        fb = os.environ.get("FFMPEG_BINARY")
        if fb and os.path.exists(fb):
            os.environ["PATH"] = os.path.dirname(fb) + os.pathsep + os.environ.get("PATH", "")
            try:
                from pydub import AudioSegment as _AS
                _AS.converter = fb
            except Exception:
                pass
            return

        # 1) If running as frozen (.exe), try bundled ffmpeg next to the executable
        base_dir = sys._MEIPASS if getattr(sys, "frozen", False) else os.path.dirname(__file__)
        candidates = [
            os.path.join(base_dir, "ffmpeg", "bin", "ffmpeg.exe"),
            os.path.join(base_dir, "ffmpeg", "ffmpeg.exe"),
        ]

        # 2) Common local installs (manual / winget alias in WindowsApps)
        candidates += [
            r"C:\ffmpeg\bin\ffmpeg.exe",
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WindowsApps", "ffmpeg.exe"),
        ]

        for exe in candidates:
            if exe and os.path.exists(exe):
                os.environ["PATH"] = os.path.dirname(exe) + os.pathsep + os.environ.get("PATH", "")
                try:
                    from pydub import AudioSegment as _AS
                    _AS.converter = exe   # bantu pydub pakai ffmpeg ini
                except Exception:
                    pass
                break
    except Exception:
        # jangan sampai wiring bikin app crash
        pass

_wire_ffmpeg_runtime()
# ============================================================================ 


# Optional imports (may be missing in headless/sandbox environments)
try:
    import whisper
except Exception:
    whisper = None

try:
    from pydub import AudioSegment
except Exception:
    AudioSegment = None

# Attempt to import tkinter but do not fail if it's missing.
HAVE_TK = False
try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, scrolledtext
    from tkinter import ttk  # NEW: for Progressbar
    HAVE_TK = True
except Exception:
    HAVE_TK = False


def check_ffmpeg() -> bool:
    fb = os.environ.get("FFMPEG_BINARY")
    if fb and os.path.exists(fb):
        return True
    return shutil.which("ffmpeg") is not None


def convert_to_wav(filepath: str) -> str:
    """Convert an audio file to WAV using pydub/ffmpeg.
    - WAV: dipakai langsung
    - Non-WAV: coba pydub; jika tidak ada pydub, fallback ke ffmpeg CLI
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Input file not found: {filepath}")

    ext = os.path.splitext(filepath)[1].lower()
    if ext == ".wav":
        return filepath

    # Target wav temp
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".wav")
    os.close(tmp_fd)

    # 1) Coba pydub (jika tersedia)
    if AudioSegment is not None:
        if not check_ffmpeg():
            # pydub butuh ffmpeg juga
            raise RuntimeError("ffmpeg not found in PATH. Install ffmpeg and ensure it's on PATH.")
        audio = AudioSegment.from_file(filepath)
        audio.export(tmp_path, format="wav")
        return tmp_path

    # 2) Fallback: gunakan ffmpeg CLI langsung
    if check_ffmpeg():
        try:
            # -y: overwrite, -i: input, output: tmp_path
            subprocess.run(
                ["ffmpeg", "-y", "-i", filepath, tmp_path],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            return tmp_path
        except subprocess.CalledProcessError as e:
            # Jika ffmpeg gagal, bersihkan file tmp lalu lempar error informatif
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass
            raise RuntimeError(f"ffmpeg failed to convert file: {e.stderr.decode(errors='ignore')[:500]}")

    # 3) Tidak ada pydub dan ffmpeg → kasih petunjuk
    raise RuntimeError(
        "Cannot convert audio to WAV: neither pydub nor ffmpeg CLI available.\n"
        "- Install pydub: pip install pydub (but still needs ffmpeg), or\n"
        "- Install ffmpeg and ensure it's on PATH."
    )



def transcribe_file(filepath: str, model_name: str = "small") -> str:
    """(Tetap ada) Transcribe satu kali tanpa progress (compat)."""
    if whisper is None:
        raise RuntimeError("The 'whisper' package is not installed. Install with: pip install openai-whisper")

    wav_path = None
    try:
        wav_path = convert_to_wav(filepath)
        model = whisper.load_model(model_name)
        # Tambahkan verbose=False agar tqdm tidak muncul
        result = model.transcribe(wav_path, verbose=False)
        return result.get("text", "")
    finally:
        try:
            if wav_path and wav_path != filepath and wav_path.startswith(tempfile.gettempdir()):
                os.remove(wav_path)
        except Exception:
            pass



# ===== NEW: transcribe dengan progress =====
def transcribe_file_with_progress(
    filepath: str,
    model_name: str = "small",
    progress_cb=None,
    chunk_seconds: int = 30
) -> str:
    """
    Transcribe audio per-chunk sambil memanggil progress_cb(percent:int).
    Jika pydub tidak tersedia, akan jatuh ke mode 'indeterminate' (tetap transcribe utuh).
    """
    if whisper is None:
        raise RuntimeError("The 'whisper' package is not installed. Install with: pip install openai-whisper")

    wav_path = None
    tmp_chunks = []  # daftar file sementara chunk
    try:
        # 1) Konversi ke WAV bila perlu
        wav_path = convert_to_wav(filepath)

        # 2) Hitung durasi total (ms) bila memungkinkan
        total_ms = None
        audio_seg = None
        if AudioSegment is not None:
            try:
                audio_seg = AudioSegment.from_file(wav_path)
                total_ms = len(audio_seg)
            except Exception:
                audio_seg = None
                total_ms = None

        # 3) Load model
        model = whisper.load_model(model_name)

        # Jika tidak bisa ukur durasi, jalankan sekali (no %); tetap panggil 0 dan 100 agar GUI gerak
        if total_ms is None or audio_seg is None:
            if progress_cb:
                progress_cb(0, note="Starting…")
            # Tambahkan verbose=False
            result = model.transcribe(wav_path, verbose=False)
            if progress_cb:
                progress_cb(100, note="Done")
            return result.get("text", "")

        # 4) Potong menjadi chunk per N detik
        chunk_ms = max(1, int(chunk_seconds * 1000))
        total_chunks = max(1, math.ceil(total_ms / chunk_ms))
        processed_ms = 0
        texts = []

        if progress_cb:
            progress_cb(0, note=f"Preparing {total_chunks} chunks…")

        # Loop chunks
        for i in range(total_chunks):
            start = i * chunk_ms
            end = min((i + 1) * chunk_ms, total_ms)
            piece = audio_seg[start:end]

            # Simpan chunk ke file sementara
            fd, tmp_chunk = tempfile.mkstemp(suffix=f".part{i}.wav")
            os.close(fd)
            piece.export(tmp_chunk, format="wav")
            tmp_chunks.append(tmp_chunk)

            # Transcribe chunk dengan verbose=False
            res = model.transcribe(tmp_chunk, verbose=False)
            texts.append(res.get("text", ""))

            # Update progress
            processed_ms = end
            percent = int(processed_ms * 100 / total_ms)
            if progress_cb:
                progress_cb(percent, note=f"Chunk {i+1}/{total_chunks}")

        if progress_cb:
            progress_cb(100, note="Done")
        return " ".join(texts)

    finally:
        # cleanup chunks & temp wav
        for p in tmp_chunks:
            try:
                os.remove(p)
            except Exception:
                pass
        try:
            if wav_path and wav_path != filepath and wav_path.startswith(tempfile.gettempdir()):
                os.remove(wav_path)
        except Exception:
            pass



# ---------------- GUI (only defined if HAVE_TK) ----------------
if HAVE_TK:
    class M4AToTextApp:
        def __init__(self, root):
            self.root = root
            root.title("M4A -> Text Transcriber")
            root.geometry("760x560")  # sedikit lebih tinggi untuk progressbar

            # File selection
            frm_top = tk.Frame(root)
            frm_top.pack(fill=tk.X, padx=10, pady=6)

            self.file_path_var = tk.StringVar()
            tk.Label(frm_top, text="File:").pack(side=tk.LEFT)
            tk.Entry(frm_top, textvariable=self.file_path_var, width=60).pack(side=tk.LEFT, padx=6)
            tk.Button(frm_top, text="Browse", command=self.browse_file).pack(side=tk.LEFT)

            # Model choice
            frm_model = tk.Frame(root)
            frm_model.pack(fill=tk.X, padx=10, pady=6)
            tk.Label(frm_model, text="Whisper model:").pack(side=tk.LEFT)
            self.model_var = tk.StringVar(value="small")
            tk.OptionMenu(frm_model, self.model_var, "tiny", "base", "small", "medium", "large").pack(side=tk.LEFT)

            # Buttons
            frm_buttons = tk.Frame(root)
            frm_buttons.pack(fill=tk.X, padx=10, pady=6)
            self.btn_transcribe = tk.Button(frm_buttons, text="Transcribe", command=self.start_transcription)  # NEW keep ref
            self.btn_transcribe.pack(side=tk.LEFT)
            tk.Button(frm_buttons, text="Save Transcript", command=self.save_transcript).pack(side=tk.LEFT, padx=6)
            tk.Button(frm_buttons, text="Clear", command=self.clear_text).pack(side=tk.LEFT)

            # Status
            self.status_var = tk.StringVar(value="Ready")
            tk.Label(root, textvariable=self.status_var).pack(anchor=tk.W, padx=12)

            # NEW: Progressbar + label
            frm_prog = tk.Frame(root)
            frm_prog.pack(fill=tk.X, padx=10, pady=(0, 6))
            self.prog = ttk.Progressbar(frm_prog, orient="horizontal", mode="determinate", maximum=100)
            self.prog.pack(fill=tk.X)
            self.prog_label = tk.Label(root, text="Progress: 0%")
            self.prog_label.pack(anchor=tk.W, padx=12)
            self._set_progress(0, "Idle")

            # Transcript area
            self.text_area = scrolledtext.ScrolledText(root, wrap=tk.WORD, font=("Consolas", 11))
            self.text_area.pack(expand=True, fill=tk.BOTH, padx=10, pady=6)

        def browse_file(self):
            fp = filedialog.askopenfilename(
                title="Select audio file",
                filetypes=[
                    ("Audio files", "*.mp3 *.wav *.m4a *.flac"),  # <- pola dipisah SPASI
                    ("MP3", "*.mp3"),
                    ("WAV", "*.wav"),
                    ("M4A", "*.m4a"),
                    ("All files", "*.*"),
                ]
            )
            if fp:
                self.file_path_var.set(fp)

        def clear_text(self):
            self.text_area.delete(1.0, tk.END)

        def save_transcript(self):
            content = self.text_area.get(1.0, tk.END).strip()
            if not content:
                messagebox.showinfo("Empty", "No transcript to save.")
                return
            fp = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text files", "*.txt")])
            if not fp:
                return
            with open(fp, "w", encoding="utf-8") as f:
                f.write(content)
            messagebox.showinfo("Saved", f"Transcript saved to:\n{fp}")

        def start_transcription(self):
            fp = self.file_path_var.get().strip()
            if not fp or not os.path.exists(fp):
                messagebox.showwarning("File missing", "Please choose a valid audio file first.")
                return
            model_name = self.model_var.get()

            # Disable button saat proses
            self.btn_transcribe.config(state="disabled")         # NEW
            self._set_progress(0, "Starting…")                   # NEW

            # Run in background thread to keep UI responsive
            t = threading.Thread(target=self._transcribe, args=(fp, model_name), daemon=True)
            t.start()

        def _transcribe(self, filepath, model_name):
            try:
                self._set_status("Converting audio (if needed)…")
                self._set_progress(0, "Preparing…")

                def gui_cb(percent, note=""):
                    # Dipanggil dari thread worker → gunakan after
                    self.root.after(0, lambda: self._set_progress(percent, note))

                self._set_status(f"Loading model '{model_name}' (this may take a while)…")

                # Panggil versi progress
                text = transcribe_file_with_progress(filepath, model_name, progress_cb=gui_cb, chunk_seconds=30)

                self._set_status("Done")
                self._set_progress(100, "Done")

                self.text_area.delete(1.0, tk.END)
                self.text_area.insert(tk.END, text)
            except Exception as e:
                tb = traceback.format_exc()
                try:
                    messagebox.showerror("Error", f"An error occurred:\n{e}\n\nTrace:\n{tb}")
                except Exception:
                    print("Error while showing messagebox:", e)
                    print(tb)
                self._set_status("Error")
                self._set_progress(0, "Error")
            finally:
                # Re-enable tombol
                self.root.after(0, lambda: self.btn_transcribe.config(state="normal"))

        def _set_status(self, msg):
            self.root.after(0, lambda: self.status_var.set(msg))

        # NEW: helper update progressbar & label
        def _set_progress(self, percent: int, note: str = ""):
            percent = max(0, min(100, int(percent)))
            self.prog["value"] = percent
            label = f"Progress: {percent}%"
            if note:
                label += f" — {note}"
            self.prog_label.config(text=label)
            self.prog.update_idletasks()


# ---------------- CLI implementation ----------------

def cli_check():
    print("Environment check:")
    print("  Python:", sys.version.replace('\n', '\\n         '))
    print("  Tkinter available:", HAVE_TK)
    print("  whisper installed:", whisper is not None)
    print("  pydub installed:", AudioSegment is not None)
    print("  ffmpeg on PATH:", check_ffmpeg())


def run_cli(args=None):
    """
    Parse CLI args and run the requested action.
    """
    parser = argparse.ArgumentParser(description="M4A -> Text Transcriber (CLI fallback)")
    parser.add_argument("--file", "-f", help="Path to input audio file (.m4a, .mp3, .wav, .flac)")
    parser.add_argument("--model", "-m", default="small", help="Whisper model to use (tiny, base, small, medium, large)")
    parser.add_argument("--output", "-o", help="Path to save transcript (optional). If omitted, transcript printed to stdout.")
    parser.add_argument("--check", action="store_true", help="Print environment/dependency checks and exit")
    parser.add_argument("--run-tests", action="store_true", help="Run lightweight internal tests and exit")

    parsed = parser.parse_args(args=args)

    if parsed.run_tests:
        try:
            run_unit_tests()
            return 0
        except AssertionError as ae:
            print("Tests failed:", ae)
            return 1

    if parsed.check:
        cli_check()
        return 0

    if not parsed.file:
        if sys.stdin is not None and sys.stdin.isatty():
            try:
                user_input = input("No --file provided. Enter path to audio file (leave empty to abort): ").strip()
            except Exception:
                user_input = ""
            if not user_input:
                print("No file provided. Aborting gracefully.")
                return 0
            parsed.file = user_input
        else:
            parser.print_help()
            print("\nNote: --file is required in non-GUI, non-interactive mode.\nIf you expected a GUI, run without arguments on a system with Tkinter available.")
            return 0

    try:
        print(f"Transcribing '{parsed.file}' with model '{parsed.model}'...")

        # NEW: CLI progress callback
        last_p = -1
        def cli_cb(p, note=""):
            nonlocal last_p
            if p != last_p:
                print(f"\rProgress: {p:3d}% {note:20s}", end="", flush=True)
                last_p = p

        text = transcribe_file_with_progress(parsed.file, parsed.model, progress_cb=cli_cb, chunk_seconds=30)
        print("\rProgress: 100% Done               ")

        if parsed.output:
            with open(parsed.output, "w", encoding="utf-8") as f:
                f.write(text)
            print(f"\nTranscript saved to: {parsed.output}")
        else:
            print("\n--- Transcript start ---\n")
            print(text)
            print("\n--- Transcript end ---\n")
        return 0
    except Exception as e:
        print("\nAn error occurred:", e)
        tb = traceback.format_exc()
        print(tb)
        return 1


# ---------------- Lightweight internal tests ----------------
def run_unit_tests():
    # tetap sama
    val = check_ffmpeg()
    assert isinstance(val, bool), "check_ffmpeg() must return a boolean"

    missing = "__definitely_nonexistent_audio_file_12345__.m4a"
    try:
        convert_to_wav(missing)
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("convert_to_wav should raise FileNotFoundError for missing file")

    rc = run_cli(["--check"])
    assert rc == 0, f"run_cli(['--check']) returned {rc}"

    rc2 = run_cli(["--file", missing])
    assert rc2 != 0, "run_cli should return non-zero for a missing input file"

    print("All internal tests passed.")


# ---------------- Main entrypoint ----------------
def main(argv=None):
    if HAVE_TK:
        try:
            root = tk.Tk()
            app = M4AToTextApp(root)
            root.mainloop()
            return 0
        except Exception as e:
            print("Failed to start Tkinter GUI. Falling back to CLI. Error:", e, file=sys.stderr)
            print(traceback.format_exc(), file=sys.stderr)
            return run_cli(argv)
    else:
        return run_cli(argv)


def safe_exit(rc: int = 0):
    try:
        os._exit(int(rc) if isinstance(rc, int) else 0)
    except Exception:
        try:
            sys.exit(int(rc) if isinstance(rc, int) else 0)
        except SystemExit:
            pass


if __name__ == "__main__":
    try:
        rc = main(sys.argv[1:])
    except SystemExit as se:
        code = se.code if hasattr(se, "code") else 1
        safe_exit(code if code is not None else 0)
    except Exception:
        print("Unhandled exception in main:\n", traceback.format_exc(), file=sys.stderr)
        safe_exit(1)
    else:
        safe_exit(rc if rc is not None else 0)