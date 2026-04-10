import tkinter as tk
from tkinter import filedialog, scrolledtext, messagebox
import threading
import subprocess
import os
import shutil


class ConverterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("ANSYS → Abaqus Converter")
        self.root.geometry("700x800")
        self.root.resizable(False, False)

        self.db_path = tk.StringVar()
        self.output_dir = tk.StringVar()
        self.abaqus_cmd = tk.StringVar(value="abaqus")
        self.node_tol = tk.StringVar(value="1e-6")

        # MAPDL launch settings
        self.mapdl_version = tk.StringVar(value="242")
        self.nproc = tk.StringVar(value="4")
        self.ram = tk.StringVar(value="")
        self.license_type = tk.StringVar(value="ansys")
        self.extra_switches = tk.StringVar(value="")

        self._build_ui()

    def _build_ui(self):
        # --- File Selection ---
        frm_file = tk.LabelFrame(self.root, text="File Selection", padx=10, pady=5)
        frm_file.pack(fill="x", padx=10, pady=(10, 5))

        tk.Label(frm_file, text="ANSYS .db:").grid(row=0, column=0, sticky="w")
        tk.Entry(frm_file, textvariable=self.db_path, width=55).grid(row=0, column=1, padx=5)
        tk.Button(frm_file, text="Browse", command=self._browse_db).grid(row=0, column=2)

        tk.Label(frm_file, text="Output Dir:").grid(row=1, column=0, sticky="w", pady=(5, 0))
        tk.Entry(frm_file, textvariable=self.output_dir, width=55).grid(row=1, column=1, padx=5, pady=(5, 0))
        tk.Button(frm_file, text="Browse", command=self._browse_outdir).grid(row=1, column=2, pady=(5, 0))

        # --- Settings ---
        frm_set = tk.LabelFrame(self.root, text="Settings", padx=10, pady=5)
        frm_set.pack(fill="x", padx=10, pady=5)

        tk.Label(frm_set, text="Abaqus Command:").grid(row=0, column=0, sticky="w")
        tk.Entry(frm_set, textvariable=self.abaqus_cmd, width=20).grid(row=0, column=1, sticky="w", padx=5)

        tk.Label(frm_set, text="Node Merge Tol:").grid(row=0, column=2, sticky="w", padx=(20, 0))
        tk.Entry(frm_set, textvariable=self.node_tol, width=12).grid(row=0, column=3, sticky="w", padx=5)

        # --- MAPDL Launch Settings ---
        frm_mapdl = tk.LabelFrame(self.root, text="MAPDL Launch Settings", padx=10, pady=5)
        frm_mapdl.pack(fill="x", padx=10, pady=5)

        tk.Label(frm_mapdl, text="Version:").grid(row=0, column=0, sticky="w")
        tk.Entry(frm_mapdl, textvariable=self.mapdl_version, width=10).grid(row=0, column=1, sticky="w", padx=5)

        tk.Label(frm_mapdl, text="Processors:").grid(row=0, column=2, sticky="w", padx=(15, 0))
        tk.Entry(frm_mapdl, textvariable=self.nproc, width=6).grid(row=0, column=3, sticky="w", padx=5)

        tk.Label(frm_mapdl, text="RAM MB (blank=auto):").grid(row=0, column=4, sticky="w", padx=(15, 0))
        tk.Entry(frm_mapdl, textvariable=self.ram, width=8).grid(row=0, column=5, sticky="w", padx=5)

        tk.Label(frm_mapdl, text="License Type:").grid(row=1, column=0, sticky="w", pady=(5, 0))
        license_options = ["ansys", "mech", "struct", "dyna", "preppost", "enterprise"]
        tk.OptionMenu(frm_mapdl, self.license_type, *license_options).grid(row=1, column=1, sticky="w", padx=5, pady=(5, 0))

        tk.Label(frm_mapdl, text="Extra Switches:").grid(row=1, column=2, sticky="w", padx=(15, 0), pady=(5, 0))
        tk.Entry(frm_mapdl, textvariable=self.extra_switches, width=30).grid(
            row=1, column=3, columnspan=3, sticky="w", padx=5, pady=(5, 0)
        )

        # --- Step 3: Remove Blocks ---
        frm_blk = tk.LabelFrame(self.root, text="Step 3 - CDB Command Blocks to Remove (one per line)", padx=10, pady=5)
        frm_blk.pack(fill="x", padx=10, pady=5)

        self.txt_blocks = tk.Text(frm_blk, height=5, width=80)
        self.txt_blocks.pack(fill="x")
        self.txt_blocks.insert("1.0", "CECMOD\nCE\n/COM,ANSYS RELEASE")

        # --- Run ---
        frm_run = tk.Frame(self.root, pady=5)
        frm_run.pack(fill="x", padx=10)

        self.run_until = tk.StringVar(value="Step 4 (Full)")
        tk.Label(frm_run, text="Run up to:").pack(side="left", padx=(0, 5))
        step_options = [
            "Step 1&2 (Cleanup + CDWRITE)",
            "Step 3 (CDB Text Clean)",
            "Step 4 (Full)",
        ]
        tk.OptionMenu(frm_run, self.run_until, *step_options).pack(side="left", padx=(0, 15))
        self.btn_run = tk.Button(frm_run, text="Run", command=self._run, width=14, height=2)
        self.btn_run.pack(side="left")

        # --- Log ---
        frm_log = tk.LabelFrame(self.root, text="Log", padx=10, pady=5)
        frm_log.pack(fill="both", expand=True, padx=10, pady=(5, 10))

        self.log = scrolledtext.ScrolledText(frm_log, height=15, state="disabled", wrap="word")
        self.log.pack(fill="both", expand=True)

    # --- UI callbacks ---
    def _browse_db(self):
        path = filedialog.askopenfilename(filetypes=[("ANSYS DB", "*.db"), ("All", "*.*")])
        if path:
            self.db_path.set(path)
            if not self.output_dir.get():
                self.output_dir.set(os.path.dirname(path))

    def _browse_outdir(self):
        path = filedialog.askdirectory()
        if path:
            self.output_dir.set(path)

    def _log(self, msg):
        self.log.config(state="normal")
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.log.config(state="disabled")
        self.root.update_idletasks()

    def _run(self):
        if not self.db_path.get():
            messagebox.showwarning("Warning", "Select an ANSYS .db file first.")
            return
        self.btn_run.config(state="disabled")
        threading.Thread(target=self._run_pipeline, daemon=True).start()

    # --- Pipeline ---
    def _run_pipeline(self):
        until = self.run_until.get()
        try:
            self._step1_and_2()
            if "Step 1&2" in until:
                self._log("\n=== Stopped after Step 1&2 ===")
                return

            cdb_path = self._step3_clean_cdb()
            if "Step 3" in until:
                self._log("\n=== Stopped after Step 3 ===")
                return

            self._step4_convert(cdb_path)
            self._log("\n=== All steps completed ===")
        except Exception as e:
            self._log(f"\n[ERROR] {e}")
        finally:
            self.btn_run.config(state="normal")

    def _step1_and_2(self):
        """PyMAPDL: cleanup model and CDWRITE"""
        self._log("=== Step 1 & 2: PyMAPDL cleanup + CDWRITE ===")

        from ansys.mapdl.core import launch_mapdl

        out_dir = self.output_dir.get()

        version_str = self.mapdl_version.get().strip()
        if version_str:
            try:
                version = int(version_str)
            except ValueError:
                raise ValueError(f"MAPDL Version must be an integer (e.g. 192, 211, 242). Got: '{version_str}'")
        else:
            version = 242

        nproc = int(self.nproc.get().strip()) if self.nproc.get().strip() else 4
        ram = int(self.ram.get().strip()) if self.ram.get().strip() else None
        license_type = self.license_type.get().strip() or "ansys"
        extra_switches = self.extra_switches.get().strip() or ""

        mapdl = launch_mapdl(
            run_location=out_dir,
            override=True,
            version=version,
            nproc=nproc,
            ram=ram,
            license_type=license_type,
            additional_switches=extra_switches,
        )
        self._log(f"MAPDL launched (v{mapdl.version})")

        try:
            # Resume .db — MAPDL은 run_location 기준으로 파일을 찾으므로
            # .db 파일을 run_location에 복사 후 파일명만 전달
            db_src = self.db_path.get()
            db_dst = os.path.join(out_dir, os.path.basename(db_src))
            if os.path.normpath(db_src) != os.path.normpath(db_dst):
                shutil.copy2(db_src, db_dst)
                self._log(f"Copied .db to run_location: {db_dst}")
            db_name = os.path.splitext(os.path.basename(db_src))[0]
            mapdl.resume(db_name, "db")
            self._log(f"Resumed: {db_name}")

            mapdl.prep7()

            # --- Step 1: Cleanup ---
            self._log("Merging duplicate nodes...")
            tol = float(self.node_tol.get())
            mapdl.nummrg("NODE", tol)

            # 미사용 물성 삭제
            self._log("Removing unused material properties...")
            self._remove_unused_mats(mapdl)

            # 넘버링 압축 (MAT 제외 - 물성 번호는 압축하지 않음)
            self._log("Compressing numbering...")
            for entity in ["NODE", "ELEM", "REAL", "TYPE"]:
                mapdl.numcmp(entity)

            mapdl.allsel("ALL")

            # --- Step 2a: 새 DB 저장 (원본 오염 방지) ---
            db_name = "clean_model"
            self._log(f"Saving cleaned model as {db_name}.db ...")
            mapdl.save(db_name, "db")
            self._log(f"{db_name}.db saved.")

            # --- Step 2b: CDWRITE ---
            cdb_name = "clean_model"
            self._log(f"Writing {cdb_name}.cdb ...")
            mapdl.cdwrite("DB", cdb_name, "cdb")
            self._log("CDWRITE complete.")

        finally:
            mapdl.exit()
            self._log("MAPDL closed.")

    def _remove_unused_mats(self, mapdl):
        """미사용 물성 찾아서 삭제 — MAPDL 매크로 방식"""
        mapdl.allsel("ALL")
        elem_count = int(mapdl.get("NELEM", "ELEM", "", "COUNT"))

        if elem_count == 0:
            self._log("  No elements found, skipping.")
            return

        # ── 1) 사용 중인 MAT 번호 수집 (*VGET) ──
        max_enum = int(mapdl.get("MAXE", "ELEM", "", "NUM", "MAX"))
        try:
            mapdl.run(f"*DIM,_MATARR,ARRAY,{max_enum}")
            mapdl.run("*VGET,_MATARR(1),ELEM,1,ATTR,MAT")
            mat_array = mapdl.parameters["_MATARR"].flatten()
            used_mats = sorted(set(mat_array[mat_array > 0].astype(int).tolist()))
        except Exception:
            self._log("  Warning: Could not bulk-read element MAT attrs, skipping.")
            return

        mat_count = int(mapdl.get("NMAT", "MAT", "", "COUNT"))
        self._log(f"  {len(used_mats)} material(s) in use, {mat_count} defined.")

        if mat_count == 0 or mat_count <= len(used_mats):
            self._log("  Nothing to delete.")
            return

        # ── 2) MAPDL 매크로로 순회+삭제를 한번에 처리 ──
        num_used = len(used_mats)
        mat_max = int(mapdl.get("MATMAX", "MAT", "", "NUM", "MAX"))
        self._log(f"  Max material number = {mat_max}")

        macro_path = os.path.join(mapdl.directory, "_del_unused_mats.mac")
        with open(macro_path, "w") as f:
            # 사용 중인 MAT ID → 배열
            f.write(f"*DIM,_USED,ARRAY,{max(num_used, 1)}\n")
            for i, mid in enumerate(used_mats, 1):
                f.write(f"_USED({i})={mid}\n")

            # Phase 1: NXTH 순회 (루프 범위 = 최대 물성 번호)
            f.write(f"*DIM,_DELARR,ARRAY,{max(mat_count, 1)}\n")
            f.write("_MID=0\n")
            f.write("_DELN=0\n")
            f.write(f"*DO,_I,1,{mat_max}\n")
            f.write("  *GET,_MID,MAT,_MID,NXTH\n")
            f.write("  *IF,_MID,GT,0,THEN\n")
            f.write("    _SKIP=0\n")
            f.write(f"    *DO,_J,1,{num_used}\n")
            f.write("      *IF,_MID,EQ,_USED(_J),THEN\n")
            f.write("        _SKIP=1\n")
            f.write("      *ENDIF\n")
            f.write("    *ENDDO\n")
            f.write("    *IF,_SKIP,EQ,0,THEN\n")
            f.write("      _DELN=_DELN+1\n")
            f.write("      _DELARR(_DELN)=_MID\n")
            f.write("    *ENDIF\n")
            f.write("  *ELSE\n")
            f.write("    *EXIT\n")
            f.write("  *ENDIF\n")
            f.write("*ENDDO\n")

            # Phase 2: 수집된 미사용 MAT 삭제
            f.write("*IF,_DELN,GT,0,THEN\n")
            f.write("  *DO,_I,1,_DELN\n")
            f.write("    MPDELE,ALL,_DELARR(_I)\n")
            f.write("    TBDELE,ALL,_DELARR(_I)\n")
            f.write("  *ENDDO\n")
            f.write("*ENDIF\n")

        mapdl.input(macro_path)

        try:
            deleted = int(float(mapdl.parameters["_DELN"]))
        except Exception:
            deleted = 0
        self._log(f"  Deleted {deleted} unused material(s).")

    def _step3_clean_cdb(self):
        """CDB 텍스트에서 불필요한 커맨드 블록 제거"""
        self._log("\n=== Step 3: CDB text cleanup ===")

        out_dir = self.output_dir.get()
        src = os.path.join(out_dir, "clean_model.cdb")
        dst = os.path.join(out_dir, "clean_model_trimmed.cdb")

        remove_blocks = [
            line.strip()
            for line in self.txt_blocks.get("1.0", "end").splitlines()
            if line.strip()
        ]

        if not remove_blocks:
            self._log("No blocks to remove, copying as-is.")
            shutil.copy(src, dst)
            return dst

        self._log(f"Removing blocks starting with: {remove_blocks}")

        with open(src, "r") as f:
            lines = f.readlines()

        out_lines = []
        skip = False
        removed_count = 0

        for line in lines:
            stripped = line.strip()
            if any(stripped.startswith(b) for b in remove_blocks):
                skip = True
                removed_count += 1
                continue
            # 새 블록 시작 시 (들여쓰기 없는 비어있지 않은 줄) skip 해제
            if skip and stripped and not line[0].isspace():
                skip = False
            if not skip:
                out_lines.append(line)

        with open(dst, "w") as f:
            f.writelines(out_lines)

        self._log(f"Removed {removed_count} block(s). Saved: {dst}")
        return dst

    def _step4_convert(self, cdb_path):
        """abaqus fromansys 실행"""
        self._log("\n=== Step 4: abaqus fromansys ===")

        out_dir = self.output_dir.get()
        job_name = "converted_model"
        # 확장자 제거
        input_name = os.path.splitext(os.path.basename(cdb_path))[0]

        cmd = f'{self.abaqus_cmd.get()} fromansys job={job_name} input={input_name}'
        self._log(f"Running: {cmd}")

        result = subprocess.run(
            cmd, shell=True, cwd=out_dir,
            capture_output=True, text=True
        )

        if result.stdout:
            self._log(result.stdout)
        if result.stderr:
            self._log(result.stderr)

        inp_path = os.path.join(out_dir, f"{job_name}.inp")
        log_path = os.path.join(out_dir, f"{job_name}.log")

        if os.path.exists(inp_path):
            self._log(f"INP created: {inp_path}")
        else:
            self._log("[WARNING] INP file not found - check log for errors.")

        if os.path.exists(log_path):
            self._log(f"\n--- Conversion Log ({job_name}.log) ---")
            with open(log_path, "r") as f:
                self._log(f.read())


if __name__ == "__main__":
    root = tk.Tk()
    app = ConverterApp(root)
    root.mainloop()
