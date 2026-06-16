import tkinter as tk
from tkinter import filedialog, scrolledtext, messagebox
import threading
import os
import shutil

from . import mapdl_ops, cdb_utils, inp_writer, utils


class ConverterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("ANSYS → Abaqus Converter")
        self.root.geometry("700x800")
        self.root.resizable(False, False)

        self.db_path = tk.StringVar()
        self.output_dir = tk.StringVar()
        self.data_dir = tk.StringVar()
        self.abaqus_cmd = tk.StringVar(value="abaqus")
        self.node_tol = tk.StringVar(value="1e-6")
        # UNBLOCKED CDWRITE format expands ETBLOCK into classic ET/KEYOPT
        # cards so older HyperMesh versions can read the .cdb. Default on.
        # NOTE: abaqus fromansys (Step 4) requires BLOCKED nblock/eblock,
        # so a full Step 4 run forces BLOCKED regardless of this flag.
        self.cdwrite_unblocked = tk.BooleanVar(value=True)
        self.mapdl_version = tk.StringVar(value="242")
        self.nproc = tk.StringVar(value="4")
        self.license_type = tk.StringVar(value="preppost")

        self._step1_log_path = None
        self._build_ui()

    # -----------------------------------------------------------------------
    # UI construction
    # -----------------------------------------------------------------------

    def _build_ui(self):
        frm_file = tk.LabelFrame(self.root, text="File Selection", padx=10, pady=5)
        frm_file.pack(fill="x", padx=10, pady=(10, 5))

        tk.Label(frm_file, text="ANSYS .db:").grid(row=0, column=0, sticky="w")
        tk.Entry(frm_file, textvariable=self.db_path, width=55).grid(row=0, column=1, padx=5)
        tk.Button(frm_file, text="Browse", command=self._browse_db).grid(row=0, column=2)

        frm_set = tk.LabelFrame(self.root, text="Settings", padx=10, pady=5)
        frm_set.pack(fill="x", padx=10, pady=5)

        tk.Label(frm_set, text="Abaqus Command:").grid(row=0, column=0, sticky="w")
        tk.Entry(frm_set, textvariable=self.abaqus_cmd, width=20).grid(row=0, column=1, sticky="w", padx=5)

        tk.Label(frm_set, text="Node Merge Tol:").grid(row=0, column=2, sticky="w", padx=(20, 0))
        tk.Entry(frm_set, textvariable=self.node_tol, width=12).grid(row=0, column=3, sticky="w", padx=5)

        tk.Checkbutton(
            frm_set,
            text="CDWRITE UNBLOCKED (HyperMesh compatible; auto-disabled for full Step 4 run)",
            variable=self.cdwrite_unblocked,
        ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(5, 0))

        frm_mapdl = tk.LabelFrame(self.root, text="MAPDL Launch Settings", padx=10, pady=5)
        frm_mapdl.pack(fill="x", padx=10, pady=5)

        tk.Label(frm_mapdl, text="Version:").grid(row=0, column=0, sticky="w")
        tk.Entry(frm_mapdl, textvariable=self.mapdl_version, width=10).grid(row=0, column=1, sticky="w", padx=5)

        tk.Label(frm_mapdl, text="Processors:").grid(row=0, column=2, sticky="w", padx=(15, 0))
        tk.Entry(frm_mapdl, textvariable=self.nproc, width=6).grid(row=0, column=3, sticky="w", padx=5)

        tk.Label(frm_mapdl, text="License Type:").grid(row=1, column=0, sticky="w", pady=(5, 0))
        license_options = ["preppost", "ansys", "mech", "struct", "dyna", "enterprise"]
        tk.OptionMenu(frm_mapdl, self.license_type, *license_options).grid(
            row=1, column=1, sticky="w", padx=5, pady=(5, 0)
        )

        frm_run = tk.Frame(self.root, pady=5)
        frm_run.pack(fill="x", padx=10)

        self.run_until = tk.StringVar(value="Step 4 (Full)")
        tk.Label(frm_run, text="Run up to:").pack(side="left", padx=(0, 5))
        step_options = ["Step 1&2 (Cleanup + CDWRITE)", "Step 4 (Full)"]
        self.run_upto_menu = tk.OptionMenu(frm_run, self.run_until, *step_options)
        self.run_upto_menu.config(width=28, height=1)
        self.run_upto_menu.pack(side="left", padx=(0, 15))

        self.btn_run = tk.Button(
            frm_run, text="Run", command=self._run, width=14, height=1,
            bg="#2E8B57", fg="white", activebackground="#3BA66B", activeforeground="white",
        )
        self.btn_show_step1 = tk.Button(
            frm_run, text="Show Step 1 Commands", command=self._show_step1_log, width=22, height=1,
        )
        self.btn_run.pack(side="right")
        self.btn_show_step1.pack(side="right", padx=(0, 8))

        frm_log = tk.LabelFrame(self.root, text="Log", padx=10, pady=5)
        frm_log.pack(fill="both", expand=True, padx=10, pady=(5, 10))

        self.log = scrolledtext.ScrolledText(frm_log, height=15, state="disabled", wrap="word")
        self.log.pack(fill="both", expand=True)

    # -----------------------------------------------------------------------
    # UI callbacks
    # -----------------------------------------------------------------------

    def _browse_db(self):
        path = filedialog.askopenfilename(filetypes=[("ANSYS DB", "*.db"), ("All", "*.*")])
        if path:
            self.db_path.set(path)
            self.output_dir.set(os.path.dirname(path))

    def _show_step1_log(self):
        log_path = self._step1_log_path
        if not log_path or not os.path.exists(log_path):
            search_dirs = [self.data_dir.get(), self.output_dir.get()]
            for d in search_dirs:
                if not d:
                    continue
                candidate = os.path.join(d, "step1_apdl.log")
                if os.path.exists(candidate):
                    log_path = candidate
                    break
        if not log_path or not os.path.exists(log_path):
            messagebox.showinfo("Step 1 Commands", "No Step 1 APDL log found yet. Run Step 1 first.")
            return

        win = tk.Toplevel(self.root)
        win.title(f"Step 1 - MAPDL Commands ({os.path.basename(log_path)})")
        win.geometry("800x600")
        txt = scrolledtext.ScrolledText(win, wrap="none")
        txt.pack(fill="both", expand=True, padx=5, pady=5)
        try:
            with open(log_path, "r") as f:
                content = f.read()
            if not content.strip():
                content = "(log file is empty - Step 1 may still be running)"
            txt.insert("1.0", content)
        except Exception as e:
            txt.insert("1.0", f"Error reading log: {e}")
        txt.config(state="disabled")
        tk.Button(win, text="Close", command=win.destroy).pack(pady=(0, 5))

    def _log(self, msg):
        self.log.config(state="normal")
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.log.config(state="disabled")
        self.root.update_idletasks()

    def _run(self):
        db_path = self.db_path.get()
        if not db_path:
            messagebox.showwarning("Warning", "Select an ANSYS .db file first.")
            return
        out_dir = os.path.dirname(os.path.abspath(db_path))
        data_dir = os.path.join(out_dir, "_data")
        os.makedirs(data_dir, exist_ok=True)
        self.output_dir.set(out_dir)
        self.data_dir.set(data_dir)
        self.btn_run.config(state="disabled")
        threading.Thread(target=self._run_pipeline, daemon=True).start()

    # -----------------------------------------------------------------------
    # Pipeline
    # -----------------------------------------------------------------------

    def _run_pipeline(self):
        until = self.run_until.get()
        try:
            self._step1_and_2()
            if "Step 1&2" in until:
                self._log("\n=== Stopped after Step 1&2 ===")
                return
            cdb_path = os.path.join(self.data_dir.get(), "clean_model.cdb")
            self._step4_convert(cdb_path)
            self._log("\n=== All steps completed ===")
        except Exception as e:
            self._log(f"\n[ERROR] {e}")
        finally:
            self.btn_run.config(state="normal")

    def _step1_and_2(self):
        """PyMAPDL: cleanup model and CDWRITE."""
        self._log("=== Step 1 & 2: PyMAPDL cleanup + CDWRITE ===")

        from ansys.mapdl.core import launch_mapdl

        out_dir = self.data_dir.get()
        os.makedirs(out_dir, exist_ok=True)

        version_str = self.mapdl_version.get().strip()
        if version_str:
            try:
                version = int(version_str)
            except ValueError:
                raise ValueError(
                    f"MAPDL Version must be an integer (e.g. 192, 211, 242). Got: '{version_str}'"
                )
        else:
            version = 242

        nproc = int(self.nproc.get().strip()) if self.nproc.get().strip() else 4
        license_type = self.license_type.get().strip() or "preppost"

        mapdl = launch_mapdl(
            run_location=out_dir,
            override=True,
            version=version,
            nproc=nproc,
            license_type=license_type,
            additional_switches="-smp",
        )
        self._log(f"MAPDL launched (v{mapdl.version})")

        self._step1_log_path = os.path.join(out_dir, "step1_apdl.log")
        try:
            mapdl.open_apdl_log(self._step1_log_path, mode="w")
            self._log(f"APDL command log: {self._step1_log_path}")
        except Exception as e:
            self._log(f"  (APDL log not started: {e})")

        try:
            db_src = self.db_path.get()
            db_dst = os.path.join(out_dir, os.path.basename(db_src))
            if os.path.normpath(db_src) != os.path.normpath(db_dst):
                shutil.copy2(db_src, db_dst)
                self._log(f"Copied .db to run_location: {db_dst}")
            db_name = os.path.splitext(os.path.basename(db_src))[0]
            mapdl.resume(db_name, "db")
            self._log(f"Resumed: {db_name}")

            mapdl.prep7()

            self._log("Merging duplicate nodes...")
            tol = float(self.node_tol.get())
            mapdl.nummrg("NODE", tol)

            self._log("Processing tie (CE) conditions and loads...")
            mapdl_ops.handle_ties_and_loads(mapdl, self._log)

            self._log("Removing unused material properties...")
            mapdl_ops.remove_unused_mats(mapdl, self._log)

            mapdl.allsel("ALL")

            db_name = "clean_model"
            self._log(f"Saving cleaned model as {db_name}.db ...")
            mapdl.save(db_name, "db")
            self._log(f"{db_name}.db saved.")

            cdb_name = "clean_model"
            is_full_run = "Step 4" in self.run_until.get()
            user_wants_unblocked = bool(self.cdwrite_unblocked.get())
            use_unblocked = user_wants_unblocked and not is_full_run
            if user_wants_unblocked and is_full_run:
                self._log(
                    "  (UNBLOCKED requested, but full Step 4 run requires "
                    "BLOCKED for abaqus fromansys — overriding.)"
                )
            fmat = "UNBLOCKED" if use_unblocked else ""
            self._log(
                f"Writing {cdb_name}.cdb "
                f"({'UNBLOCKED' if use_unblocked else 'BLOCKED'} format) ..."
            )
            mapdl.cdwrite("DB", cdb_name, "cdb", fmat=fmat)
            self._log("CDWRITE complete.")

            if not use_unblocked:
                cdb_path = os.path.join(out_dir, f"{cdb_name}.cdb")
                expanded = cdb_utils.expand_etblock(cdb_path)
                if expanded:
                    self._log(f"  Expanded ETBLOCK -> {expanded} ET/KEYOPT card(s).")
                rewritten = cdb_utils.rewrite_mp_mpdata_to_classic(cdb_path)
                if rewritten:
                    self._log(
                        f"  Rewrote {rewritten} MP/MPDATA line(s) to "
                        f"classic format (abaqus fromansys compatible)."
                    )

            self._export_step1_metadata(mapdl, out_dir)

        finally:
            try:
                mapdl.exit()
            except Exception:
                try:
                    mapdl.exit(force=True)
                except Exception as e:
                    self._log(f"MAPDL exit warning: {e}")
            self._log("MAPDL closed.")

    def _export_step1_metadata(self, mapdl, out_dir):
        """Save nset/material metadata from MAPDL to text files."""
        nset_path = os.path.join(out_dir, "step1_nsets.txt")
        mplist_path = os.path.join(out_dir, "step1_mplist.txt")

        nset_data = mapdl_ops.collect_nset_data(mapdl, self._log)
        with open(nset_path, "w") as f:
            for name, ids in nset_data.items():
                f.write(f"[{name}]\n")
                for i in range(0, len(ids), 16):
                    f.write(", ".join(str(v) for v in ids[i:i + 16]) + "\n")
                f.write("\n")
        self._log(f"Saved nset metadata: {nset_path}")

        mapdl_ops.dump_mapdl_mplist(mapdl, mplist_path)
        self._log(f"Saved material metadata: {mplist_path}")

    def _step4_convert(self, cdb_path):
        """CDB 직접 파싱 → Abaqus INP 템플릿 생성."""
        self._log("\n=== Step 4: direct text INP build (no fromansys) ===")

        out_dir = self.output_dir.get()
        data_dir = self.data_dir.get() or out_dir
        db_src = self.db_path.get()
        inp_stem = (
            os.path.splitext(os.path.basename(db_src))[0]
            if db_src else "converted_model"
        )
        inp_path = os.path.join(out_dir, f"{inp_stem}.inp")

        nodes = cdb_utils.parse_cdb_nodes(cdb_path)
        elems_by_mat = cdb_utils.parse_cdb_elements_by_mat(cdb_path)
        nset_txt = os.path.join(data_dir, "step1_nsets.txt")
        mplist_txt = os.path.join(data_dir, "step1_mplist.txt")
        cdb_nsets = cdb_utils.parse_cdb_nsets(cdb_path)

        if os.path.exists(nset_txt):
            nsets = cdb_utils.read_nsets_txt(nset_txt)
            for k, vals in cdb_nsets.items():
                if not nsets.get(k):
                    nsets[k] = vals
        else:
            nsets = cdb_nsets

        mat_info = (
            cdb_utils.read_materials_from_mplist_txt(mplist_txt)
            if os.path.exists(mplist_txt) else {}
        )
        mat_ids = sorted(mat_info.keys()) if mat_info else sorted(elems_by_mat.keys())

        if not nodes:
            raise RuntimeError("NBLOCK에서 노드를 읽지 못했습니다.")
        if not elems_by_mat:
            raise RuntimeError("EBLOCK에서 요소를 읽지 못했습니다.")

        utils.log_node_coordinate_stats(nodes, "NBLOCK raw", self._log)
        nodes = utils.scale_nodes(nodes, 1000.0)
        utils.log_node_coordinate_stats(nodes, "Scaled x1000", self._log)
        self._log("Applied coordinate scale-up: x1000")

        inp_writer.write_template_inp(inp_path, nodes, elems_by_mat, mat_ids, nsets, mat_info, self._log)
        self._log(f"INP created: {inp_path}")
        self._log(
            "NOTE: 재료 상세(온도의존/ENG CONSTANTS/CTE)는 템플릿 자리만 생성됩니다. "
            "실제 값은 INP에서 채워주세요."
        )
