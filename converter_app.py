import tkinter as tk
from tkinter import filedialog, scrolledtext, messagebox
import threading
import subprocess
import os
import re
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
        # UNBLOCKED CDWRITE format expands ETBLOCK into classic ET/KEYOPT
        # cards so older HyperMesh versions can read the .cdb. Default on.
        # NOTE: abaqus fromansys (Step 4) requires BLOCKED nblock/eblock,
        # so a full Step 4 run forces BLOCKED regardless of this flag.
        self.cdwrite_unblocked = tk.BooleanVar(value=True)
        # Step 3 text-level CDB cleanup toggle. When disabled, the .cdb
        # produced by Step 1&2 is passed straight to Step 4.
        self.cdb_cleanup_enabled = tk.BooleanVar(value=True)

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

        tk.Checkbutton(
            frm_set,
            text="CDWRITE UNBLOCKED (HyperMesh compatible; auto-disabled for full Step 4 run)",
            variable=self.cdwrite_unblocked,
        ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(5, 0))

        tk.Checkbutton(
            frm_set,
            text="Run Step 3 CDB text cleanup",
            variable=self.cdb_cleanup_enabled,
        ).grid(row=2, column=0, columnspan=4, sticky="w")

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

        self.txt_blocks = tk.Text(frm_blk, height=12, width=80)
        self.txt_blocks.pack(fill="x")
        default_cards = [
            "/COM", "/TITLE", "DOF", "ANTYPE", "ACEL",
            "CGLOC", "CGOMGA", "DCGOMG", "DOMEGA", "IRLF",
            "OMEGA", "KUSE", "ALPHAD", "BETAD", "DMPRAT",
            "CRPLIM", "NCNV", "ERESX", "TIME", "NEQIT",
            "TREF", "BFUNIF", "TOFFST", "NUMOFF", "CECMOD",
            "CE", "UnsupportedCard",
        ]
        self.txt_blocks.insert("1.0", "\n".join(default_cards))

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
        self.btn_show_step1 = tk.Button(
            frm_run,
            text="Show Step 1 Commands",
            command=self._show_step1_log,
            width=22,
            height=2,
        )
        self.btn_show_step1.pack(side="left", padx=(10, 0))

        # Path of the APDL log produced during the most recent Step 1 run.
        self._step1_log_path = None

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

    def _show_step1_log(self):
        """Pop up a window showing the APDL commands recorded during the
        most recent Step 1 run. Falls back to <output_dir>/step1_apdl.log
        if the in-memory path isn't set yet (e.g. user opened the app and
        wants to inspect a previous run's log)."""
        log_path = self._step1_log_path
        if not log_path or not os.path.exists(log_path):
            out_dir = self.output_dir.get()
            if out_dir:
                candidate = os.path.join(out_dir, "step1_apdl.log")
                if os.path.exists(candidate):
                    log_path = candidate
        if not log_path or not os.path.exists(log_path):
            messagebox.showinfo(
                "Step 1 Commands",
                "No Step 1 APDL log found yet. Run Step 1 first.",
            )
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

            if self.cdb_cleanup_enabled.get():
                cdb_path = self._step3_clean_cdb()
            else:
                self._log("\n=== Step 3: CDB text cleanup DISABLED ===")
                cdb_path = os.path.join(self.output_dir.get(), "clean_model.cdb")
            if "Step 3" in until:
                self._log("\n=== Stopped after Step 3 ===")
                return

            # Placeholder: additional CDB adjustments between Step 3 and Step 4.
            # Details will be configured later.
            cdb_path = self._step3_5_extra(cdb_path)

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

        # Step 1에서 실제 실행되는 APDL 커맨드를 파일로 기록해서
        # "Show Step 1 Commands" 버튼으로 사용자가 검토할 수 있게 한다.
        self._step1_log_path = os.path.join(out_dir, "step1_apdl.log")
        try:
            mapdl.open_apdl_log(self._step1_log_path, mode="w")
            self._log(f"APDL command log: {self._step1_log_path}")
        except Exception as e:
            self._log(f"  (APDL log not started: {e})")

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

            # Tie(CE/CEINTF) 처리: slave/master CM 생성 → 기타 CM / CE / load 삭제
            self._log("Processing tie (CE) conditions and loads...")
            self._handle_ties_and_loads(mapdl)

            # 미사용 물성 삭제
            self._log("Removing unused material properties...")
            self._remove_unused_mats(mapdl)

            mapdl.allsel("ALL")

            # --- Step 2a: 새 DB 저장 (원본 오염 방지) ---
            db_name = "clean_model"
            self._log(f"Saving cleaned model as {db_name}.db ...")
            mapdl.save(db_name, "db")
            self._log(f"{db_name}.db saved.")

            # --- Step 2b: CDWRITE ---
            # UNBLOCKED emits ET/KEYOPT as individual cards so HyperMesh
            # can read them (default). `abaqus fromansys` however rejects
            # UNBLOCKED with "missing nblock and/or eblock data", so a
            # full Step 4 run is always forced BLOCKED regardless of the
            # user's checkbox.
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

        finally:
            mapdl.exit()
            self._log("MAPDL closed.")

    def _handle_ties_and_loads(self, mapdl):
        """Detect tie conditions defined via constraint equations (CE/CEINTF).

        CEINTF generates one CE per dependent (slave) node that couples it
        to a set of independent (master) nodes on the mating surface. We
        collect every dependent node into TIE_SLAVE and every independent
        node into TIE_MASTER, then remove all other components, all CEs,
        and all applied loads before the CDWRITE."""
        mapdl.allsel("ALL")

        # ── 1) 현재 정의된 CE 개수 확인 ──
        try:
            ce_count = int(mapdl.get("NCE", "CE", 0, "NUM", "COUNT"))
        except Exception:
            ce_count = 0
        self._log(f"  Found {ce_count} constraint equation(s).")

        slave_nodes = set()
        master_nodes = set()

        if ce_count > 0:
            equations = self._parse_celist(mapdl)
            self._log(f"  Parsed {len(equations)} CE block(s) from CELIST.")
            for dep, indeps in equations:
                if dep is not None:
                    slave_nodes.add(dep)
                master_nodes.update(indeps)
            # slave 우선 - 양쪽에 동시에 들어간 노드는 master에서 제외
            master_nodes -= slave_nodes

        created_cms = set()

        # ── 2) 노드 리스트로부터 CM 생성 (매크로로 NSEL,A 일괄 처리) ──
        if slave_nodes and self._create_cm_from_node_list(mapdl, "TIE_SLAVE", slave_nodes):
            created_cms.add("TIE_SLAVE")
            self._log(f"  Created CM TIE_SLAVE ({len(slave_nodes)} nodes)")
        if master_nodes and self._create_cm_from_node_list(mapdl, "TIE_MASTER", master_nodes):
            created_cms.add("TIE_MASTER")
            self._log(f"  Created CM TIE_MASTER ({len(master_nodes)} nodes)")

        mapdl.allsel("ALL")

        # ── 3) 보존 대상(TIE_SLAVE/TIE_MASTER)을 제외한 나머지 CM 네이밍 삭제 ──
        # CMDELE은 컴포넌트 "이름(별칭)"만 제거하며, 묶여 있던 노드/요소
        # 자체는 그대로 두기 때문에 모델 구조에는 영향이 없다.
        existing_cms = self._list_all_components(mapdl)
        deleted_cm = 0
        for name in existing_cms:
            if name.upper() in created_cms:
                continue
            try:
                mapdl.cmdele(name)
                deleted_cm += 1
            except Exception:
                pass
        self._log(f"  Removed {deleted_cm} non-tie component name(s).")

        # ── 4) 모든 하중/구속/제약방정식/커플 세트 삭제 ──
        # FDELE/DDELE/SF*DELE/BF*DELE 로 모든 하중·경계조건을,
        # CEDELE 로 제약방정식(CEINTF 결과 포함)을,
        # CPDELE 로 모든 coupled DOF set을 일괄 정리한다.
        load_cmds = [
            ("fdele", ("ALL", "ALL")),           # nodal forces
            ("ddele", ("ALL", "ALL")),           # nodal DOF constraints
            ("sfedele", ("ALL", "ALL", "ALL")),  # element surface loads
            ("sfdele", ("ALL", "ALL")),          # nodal surface loads
            ("bfdele", ("ALL", "ALL")),          # nodal body forces
            ("bfedele", ("ALL", "ALL", "ALL")),  # element body forces
            ("cedele", ("ALL",)),                # constraint equations
            ("cpdele", ("ALL",)),                # coupled DOF sets
        ]
        for cmd_name, args in load_cmds:
            try:
                getattr(mapdl, cmd_name)(*args)
            except Exception:
                pass
        self._log("  Deleted all loads / constraint equations / coupled sets.")

        # ── 5) 저장된 ARRAY/TABLE 파라미터 모두 삭제 ──
        n_arrays = self._delete_array_params(mapdl)
        self._log(f"  Deleted {n_arrays} array/table parameter(s).")

        # ── 6) 남은 사용자 정의 파라미터 일괄 삭제 (*DEL,ALL) ──
        # KABS=0 이므로 _XXX 형태의 PyMAPDL 내부 파라미터는 보존된다.
        try:
            mapdl.run("*DEL,ALL")
            self._log("  Issued *DEL,ALL (cleared user parameters).")
        except Exception as e:
            self._log(f"  Warning: *DEL,ALL failed: {e}")

    def _parse_celist(self, mapdl):
        """Dump CELIST to a text file and parse it.

        Returns a list of (dep_node, set_of_indep_nodes). The first node
        listed in each CE block is treated as the dependent (slave); all
        subsequent nodes are the independent (master) set."""
        macro_path = os.path.join(mapdl.directory, "_dump_celist.mac")
        try:
            with open(macro_path, "w") as f:
                f.write("/OUTPUT,_celist,txt\n")
                f.write("CELIST,ALL,,,ANY\n")
                f.write("/OUTPUT\n")
            mapdl.input(macro_path)
        except Exception:
            # Fallback to simpler CELIST signature
            try:
                with open(macro_path, "w") as f:
                    f.write("/OUTPUT,_celist,txt\n")
                    f.write("CELIST\n")
                    f.write("/OUTPUT\n")
                mapdl.input(macro_path)
            except Exception:
                return []

        celist_path = os.path.join(mapdl.directory, "_celist.txt")
        equations = []
        current_dep = None
        current_indep = set()
        in_eq = False

        # MAPDL CELIST 노드 라인 패턴 (두 가지 가능한 포맷 모두 수용)
        node_patterns = [
            re.compile(r"NODE\s*=\s*(\d+)", re.IGNORECASE),
            re.compile(r"^\s*(\d+)\s+[A-Za-z]{1,4}\s+[-+0-9.Ee]+"),
        ]
        header_pat = re.compile(r"CONSTRAINT\s+EQUATION", re.IGNORECASE)

        try:
            with open(celist_path, "r") as f:
                for line in f:
                    if header_pat.search(line):
                        if current_dep is not None or current_indep:
                            equations.append((current_dep, current_indep))
                        current_dep = None
                        current_indep = set()
                        in_eq = True
                        continue
                    if not in_eq:
                        continue
                    node_val = None
                    for pat in node_patterns:
                        m = pat.search(line)
                        if m:
                            try:
                                node_val = int(m.group(1))
                            except ValueError:
                                node_val = None
                            break
                    if node_val is None:
                        continue
                    if current_dep is None:
                        current_dep = node_val
                    else:
                        current_indep.add(node_val)
            if current_dep is not None or current_indep:
                equations.append((current_dep, current_indep))
        except FileNotFoundError:
            return []

        return equations

    def _delete_array_params(self, mapdl):
        """Delete every stored ARRAY or TABLE parameter in the session.

        The user treats "tables" as any stored array (both ARRAY and TABLE
        kinds defined via *DIM). We dump `*STATUS,_PRM` to a text file,
        parse out parameter rows whose type column is ARRAY or TABLE, and
        `*DEL` each one. Underscore-prefixed parameters are skipped
        because they belong to PyMAPDL internals."""
        macro_path = os.path.join(mapdl.directory, "_dump_params.mac")
        try:
            with open(macro_path, "w") as f:
                f.write("/OUTPUT,_params,txt\n")
                f.write("*STATUS,_PRM\n")
                f.write("/OUTPUT\n")
            mapdl.input(macro_path)
        except Exception:
            return 0

        params_path = os.path.join(mapdl.directory, "_params.txt")
        target_names = []
        ident_re = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
        target_types = {"ARRAY", "TABLE"}
        try:
            with open(params_path, "r") as f:
                for line in f:
                    parts = line.split()
                    if not parts:
                        continue
                    name = parts[0]
                    if not ident_re.match(name):
                        continue
                    if name.startswith("_"):
                        continue
                    if any(p.upper() in target_types for p in parts[1:]):
                        target_names.append(name)
        except FileNotFoundError:
            return 0

        deleted = 0
        for name in target_names:
            try:
                mapdl.run(f"*DEL,{name},,NOPR")
                deleted += 1
            except Exception:
                pass
        return deleted

    def _create_cm_from_node_list(self, mapdl, cm_name, nodes):
        """Select the given node numbers and save them as a NODE component.

        Uses a local macro file with chunked NSEL,A lines to avoid
        per-call round-trips through PyMAPDL."""
        if not nodes:
            return False
        macro_path = os.path.join(mapdl.directory, f"_mkcm_{cm_name}.mac")
        try:
            with open(macro_path, "w") as f:
                f.write("ALLSEL,ALL\n")
                f.write("NSEL,NONE\n")
                for node in sorted(nodes):
                    f.write(f"NSEL,A,NODE,,{node}\n")
                f.write(f"CM,{cm_name},NODE\n")
                f.write("ALLSEL,ALL\n")
            mapdl.input(macro_path)
            return True
        except Exception as e:
            self._log(f"  Warning: failed to create {cm_name}: {e}")
            return False

    def _list_all_components(self, mapdl):
        """Return a list of every currently defined component name."""
        # Prefer PyMAPDL's component manager when available
        try:
            comp = getattr(mapdl, "components", None)
            if comp is not None:
                names = list(comp.names)
                if names:
                    return names
        except Exception:
            pass

        # Fallback: dump CMLIST via macro and parse names
        macro_path = os.path.join(mapdl.directory, "_dump_cmlist.mac")
        try:
            with open(macro_path, "w") as f:
                f.write("/OUTPUT,_cmlist,txt\n")
                f.write("CMLIST\n")
                f.write("/OUTPUT\n")
            mapdl.input(macro_path)
        except Exception:
            return []

        cmlist_path = os.path.join(mapdl.directory, "_cmlist.txt")
        names = []
        valid_types = {"NODE", "ELEM", "ELEMENT", "KP", "LINE", "AREA", "VOLU"}
        try:
            with open(cmlist_path, "r") as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 2 and re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", parts[0]):
                        if parts[1].upper() in valid_types:
                            names.append(parts[0])
        except FileNotFoundError:
            pass
        return names

    def _remove_unused_mats(self, mapdl):
        """미사용 물성 찾아서 삭제 — MPLIST 파일 파싱 방식"""
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
            used_mats = set(int(x) for x in mat_array if x > 0)
        except Exception:
            self._log("  Warning: Could not bulk-read element MAT attrs, skipping.")
            return

        # ── 2) MPLIST → txt 파일로 추출 후 파싱 ──
        #   PyMAPDL이 /OUTPUT를 가로채므로 매크로 파일로 우회
        macro_path = os.path.join(mapdl.directory, "_dump_mplist.mac")
        with open(macro_path, "w") as f:
            f.write("/OUTPUT,_mplist,txt\n")
            f.write("MPLIST,ALL\n")
            f.write("/OUTPUT\n")
        mapdl.input(macro_path)
        mplist_path = os.path.join(mapdl.directory, "_mplist.txt")

        all_mats = set()
        try:
            with open(mplist_path, "r") as f:
                for line in f:
                    m = re.search(r'MATERIAL\s+NUMBER\s*=?\s*(\d+)', line, re.IGNORECASE)
                    if m:
                        all_mats.add(int(m.group(1)))
        except FileNotFoundError:
            self._log("  Warning: MPLIST output file not found, skipping.")
            return

        self._log(f"  {len(used_mats)} material(s) in use, {len(all_mats)} defined.")

        # ── 3) 미사용 MAT 삭제 ──
        unused = sorted(all_mats - used_mats)
        self._log(f"  {len(unused)} unused material(s) to delete...")

        deleted = 0
        for mid in unused:
            try:
                mapdl.mpdele("ALL", mid)
            except Exception:
                pass
            try:
                mapdl.tbdele("ALL", mid)
            except Exception:
                pass
            deleted += 1

        self._log(f"  Deleted {deleted} / {len(unused)} unused material(s).")

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

        def _line_matches(stripped_upper, patterns):
            for pat in patterns:
                pU = pat.upper()
                if stripped_upper == pU:
                    return True
                if stripped_upper.startswith(pU + ","):
                    return True
                if stripped_upper.startswith(pU + " "):
                    return True
            return False

        out_lines = []
        skip = False
        removed_count = 0

        for line in lines:
            stripped = line.strip()
            stripped_upper = stripped.upper()
            if _line_matches(stripped_upper, remove_blocks):
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

    def _step3_5_extra(self, cdb_path):
        """Placeholder stage between Step 3 and Step 4.

        Additional CDB/INP adjustments will be defined here later.
        For now this is a no-op that returns the input CDB path unchanged.
        """
        self._log("\n=== Step 3.5: (placeholder - to be configured later) ===")
        return cdb_path

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
