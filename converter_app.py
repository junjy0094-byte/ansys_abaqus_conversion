import tkinter as tk
from tkinter import filedialog, scrolledtext, messagebox
import threading
import os
import re
import shutil
from collections import defaultdict


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
        # MAPDL launch settings
        self.mapdl_version = tk.StringVar(value="242")
        self.nproc = tk.StringVar(value="4")
        self.license_type = tk.StringVar(value="preppost")

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

        # --- MAPDL Launch Settings ---
        frm_mapdl = tk.LabelFrame(self.root, text="MAPDL Launch Settings", padx=10, pady=5)
        frm_mapdl.pack(fill="x", padx=10, pady=5)

        tk.Label(frm_mapdl, text="Version:").grid(row=0, column=0, sticky="w")
        tk.Entry(frm_mapdl, textvariable=self.mapdl_version, width=10).grid(row=0, column=1, sticky="w", padx=5)

        tk.Label(frm_mapdl, text="Processors:").grid(row=0, column=2, sticky="w", padx=(15, 0))
        tk.Entry(frm_mapdl, textvariable=self.nproc, width=6).grid(row=0, column=3, sticky="w", padx=5)

        tk.Label(frm_mapdl, text="License Type:").grid(row=1, column=0, sticky="w", pady=(5, 0))
        license_options = ["preppost", "ansys", "mech", "struct", "dyna", "enterprise"]
        tk.OptionMenu(frm_mapdl, self.license_type, *license_options).grid(row=1, column=1, sticky="w", padx=5, pady=(5, 0))

        # --- Run ---
        frm_run = tk.Frame(self.root, pady=5)
        frm_run.pack(fill="x", padx=10)

        self.run_until = tk.StringVar(value="Step 4 (Full)")
        tk.Label(frm_run, text="Run up to:").pack(side="left", padx=(0, 5))
        step_options = [
            "Step 1&2 (Cleanup + CDWRITE)",
            "Step 4 (Full)",
        ]
        self.run_upto_menu = tk.OptionMenu(frm_run, self.run_until, *step_options)
        self.run_upto_menu.config(width=28, height=1)
        self.run_upto_menu.pack(side="left", padx=(0, 15))
        self.btn_run = tk.Button(
            frm_run, text="Run", command=self._run, width=14, height=1,
            bg="#2E8B57", fg="white", activebackground="#3BA66B", activeforeground="white"
        )
        self.btn_show_step1 = tk.Button(
            frm_run,
            text="Show Step 1 Commands",
            command=self._show_step1_log,
            width=22,
            height=1,
        )
        self.btn_run.pack(side="right")
        self.btn_show_step1.pack(side="right", padx=(0, 8))

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
            cdb_path = os.path.join(self.output_dir.get(), "clean_model.cdb")
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

            # When BLOCKED, the file contains ETBLOCK which `abaqus
            # fromansys` and older HyperMesh versions do not recognise.
            # Rewrite only the ETBLOCK section as classic ET/KEYOPT
            # commands; NBLOCK/EBLOCK stay intact so fromansys still
            # sees node/element data.
            if not use_unblocked:
                cdb_path = os.path.join(out_dir, f"{cdb_name}.cdb")
                expanded = self._expand_etblock(cdb_path)
                if expanded:
                    self._log(
                        f"  Expanded ETBLOCK -> {expanded} ET/KEYOPT card(s)."
                    )
                rewritten = self._rewrite_mp_mpdata_to_classic(cdb_path)
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

        nset_data = self._collect_nset_data(mapdl)
        with open(nset_path, "w") as f:
            for name, ids in nset_data.items():
                f.write(f"[{name}]\n")
                for i in range(0, len(ids), 16):
                    f.write(", ".join(str(v) for v in ids[i:i + 16]) + "\n")
                f.write("\n")
        self._log(f"Saved nset metadata: {nset_path}")

        self._dump_mapdl_mplist(mapdl, mplist_path)
        self._log(f"Saved material metadata: {mplist_path}")

    def _dump_mapdl_mplist(self, mapdl, mplist_path):
        macro_path = os.path.join(mapdl.directory, "_dump_mplist_for_step4.mac")
        with open(macro_path, "w") as f:
            f.write("/OUTPUT,_mplist_step4,txt\n")
            f.write("MPLIST,ALL\n")
            f.write("/OUTPUT\n")
        mapdl.input(macro_path)
        src = os.path.join(mapdl.directory, "_mplist_step4.txt")
        try:
            shutil.copy2(src, mplist_path)
        except Exception:
            with open(mplist_path, "w") as f:
                f.write("")

    def _collect_nset_data(self, mapdl):
        """Collect required nset lists directly from node coordinates/components."""
        mapdl.allsel("ALL")
        nnum = [int(v) for v in mapdl.mesh.nnum.tolist()]
        coords = mapdl.mesh.nodes
        node_xyz = {
            int(nid): (float(xyz[0]), float(xyz[1]), float(xyz[2]))
            for nid, xyz in zip(nnum, coords)
        }
        tol = 1.0e-12
        min_x = min(v[0] for v in node_xyz.values())
        min_y = min(v[1] for v in node_xyz.values())
        min_z = min(v[2] for v in node_xyz.values())

        bc_x = sorted(nid for nid, (x, _, _) in node_xyz.items() if abs(x - min_x) <= tol)
        bc_y = sorted(nid for nid, (_, y, _) in node_xyz.items() if abs(y - min_y) <= tol)

        xyz_candidates = [
            nid for nid, (x, y, z) in node_xyz.items()
            if abs(x - min_x) <= tol and abs(y - min_y) <= tol and abs(z - min_z) <= tol
        ]
        if xyz_candidates:
            bc_all = [min(xyz_candidates)]
        else:
            # 완전 일치 노드가 없으면 최소점에 가장 가까운 노드 1개 선택
            best = min(
                node_xyz.items(),
                key=lambda kv: abs(kv[1][0] - min_x) + abs(kv[1][1] - min_y) + abs(kv[1][2] - min_z),
            )[0]
            bc_all = [best]

        master = self._get_component_element_ids(
            mapdl,
            [
                "TIE_MASTER", "tie_master", "TIE_MAST", "MASTER_TIE", "master_tie", "MASTER_T",
                "MASTER", "master",
            ],
        )
        slave = self._get_component_element_ids(
            mapdl,
            [
                "TIE_SLAVE", "tie_slave", "TIE_SLAV", "SLAVE_TIE", "slave_tie", "SLAVE_TI",
                "SLAVE", "slave",
            ],
        )

        # 일부 모델에서는 컴포넌트명이 규칙에서 살짝 벗어나거나(예: 접두/접미)
        # 슬레이브만 이름이 달라서 누락될 수 있다. 이름 패턴 기반으로 한 번 더 보강.
        if not master:
            auto_master = self._get_component_element_ids_by_keywords(mapdl, include=("MASTER", "TIE"))
            if auto_master:
                master = auto_master
                self._log(f"  tie master fallback by name pattern: {len(master)} element(s)")
        if not slave:
            auto_slave = self._get_component_element_ids_by_keywords(mapdl, include=("SLAVE", "TIE"))
            if auto_slave:
                slave = auto_slave
                self._log(f"  tie slave fallback by name pattern: {len(slave)} element(s)")

        self._log(f"  tie element sets: master={len(master)} slave={len(slave)}")
        mapdl.allsel("ALL")

        return {
            "nset_temperature": sorted(nnum),
            "nset_bc_x": bc_x,
            "nset_bc_y": bc_y,
            "nset_bc_all": bc_all,
            # tie 계열은 node-set이 아니라 element-set으로 사용
            "master_tie": master,
            "slave_tie": slave,
        }

    def _get_component_element_ids_by_keywords(self, mapdl, include):
        """Find a component by name keywords and return its element IDs.

        Example: include=("SLAVE", "TIE") matches names like
        TIE_SLAVE, SLAVE_TIE, MY_TIE_SLAVE_SET, etc.
        """
        names = self._list_all_components(mapdl)
        if not names:
            return []
        keys = tuple(k.upper() for k in include)
        for name in names:
            up = name.upper()
            if all(k in up for k in keys):
                ids = self._get_component_element_ids(mapdl, [name])
                if ids:
                    return ids
        return []

    def _get_component_node_ids_by_keywords(self, mapdl, include):
        """Find a component by name keywords and return its node IDs."""
        names = self._list_all_components(mapdl)
        if not names:
            return []
        keys = tuple(k.upper() for k in include)
        for name in names:
            up = name.upper()
            if all(k in up for k in keys):
                ids = self._get_component_node_ids(mapdl, [name])
                if ids:
                    return ids
        return []

    def _get_selected_element_ids_from_elist(self, mapdl):
        """Parse selected element IDs from ELIST text output.

        Using ELIST avoids relying on PyMAPDL mesh cache sync and has
        proven more stable for component-based extraction.
        """
        try:
            txt = mapdl.elist()
        except Exception:
            return []
        if not txt:
            return []

        ids = set()
        for line in str(txt).splitlines():
            # ELIST 본문에서 요소 라인은 보통 숫자로 시작한다.
            m = re.match(r"^\s*(\d+)\b", line)
            if not m:
                continue
            try:
                ids.add(int(m.group(1)))
            except ValueError:
                pass
        return sorted(ids)

    def _get_component_element_ids(self, mapdl, candidates):
        existing = {name.upper(): name for name in self._list_all_components(mapdl)}
        target = None
        for c in candidates:
            if c.upper() in existing:
                target = existing[c.upper()]
                break
        if not target:
            return []

        try:
            ctype = self._get_component_type(mapdl, target)

            # allsel 누락/잔여 선택 영향 최소화를 위해 항상 초기화 후 수행
            mapdl.allsel("ALL")

            if ctype in {"ELEM", "ELEMENT"}:
                mapdl.cmsel("S", target, "ELEM")
                return sorted(set(self._get_selected_element_ids_from_elist(mapdl)))

            if ctype == "NODE":
                mapdl.cmsel("S", target, "NODE")
                try:
                    mapdl.esln("S")
                except Exception:
                    pass
                return sorted(set(self._get_selected_element_ids_from_elist(mapdl)))

            # Unknown 타입 fallback: NODE->ESLN 후 ELEM direct 순서로 시도
            mapdl.cmsel("S", target, "NODE")
            try:
                mapdl.esln("S")
            except Exception:
                pass
            eids = self._get_selected_element_ids_from_elist(mapdl)
            if eids:
                return sorted(set(eids))

            mapdl.allsel("ALL")
            mapdl.cmsel("S", target, "ELEM")
            eids = self._get_selected_element_ids_from_elist(mapdl)
            if eids:
                return sorted(set(eids))

            mapdl.allsel("ALL")
            mapdl.cmsel("S", target)
            return sorted(set(self._get_selected_element_ids_from_elist(mapdl)))
        except Exception:
            return []
        finally:
            try:
                mapdl.allsel("ALL")
            except Exception:
                pass

    def _get_component_type(self, mapdl, target_name):
        """Return component entity type from CMLIST output (NODE/ELEM/...)."""
        macro_path = os.path.join(mapdl.directory, "_dump_cmlist_type.mac")
        try:
            with open(macro_path, "w") as f:
                f.write("/OUTPUT,_cmlist_type,txt\n")
                f.write("CMLIST\n")
                f.write("/OUTPUT\n")
            mapdl.input(macro_path)
        except Exception:
            return None
        cmlist_path = os.path.join(mapdl.directory, "_cmlist_type.txt")
        try:
            with open(cmlist_path, "r") as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 2 and parts[0].upper() == target_name.upper():
                        return parts[1].upper()
        except FileNotFoundError:
            return None
        return None

    def _get_component_node_ids(self, mapdl, candidates):
        existing = {name.upper(): name for name in self._list_all_components(mapdl)}
        target = None
        for c in candidates:
            if c.upper() in existing:
                target = existing[c.upper()]
                break
        if not target:
            return []
        try:
            mapdl.allsel("ALL")
            mapdl.cmsel("S", target, "NODE")
            ids = [int(v) for v in mapdl.mesh.nnum.tolist()]
            if ids:
                return sorted(set(ids))
            # Fallback: 컴포넌트가 ELEM 타입인 경우 요소 선택 후 노드 확장
            mapdl.allsel("ALL")
            mapdl.cmsel("S", target)
            try:
                mapdl.nsle("S")
            except Exception:
                pass
            ids = [int(v) for v in mapdl.mesh.nnum.tolist()]
            return sorted(set(ids))
        except Exception:
            return []
        finally:
            try:
                mapdl.allsel("ALL")
            except Exception:
                pass

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

        # CELIST 파싱 실패/부분실패 시 기존 컴포넌트명에서 fallback
        if not slave_nodes or not master_nodes:
            existing = [n.upper() for n in self._list_all_components(mapdl)]
            if not slave_nodes and any(name in existing for name in ("TIE_SLAVE", "SLAVE_TIE", "TIE_SLAV", "SLAVE_TI")):
                slave_nodes.update(self._get_component_node_ids(mapdl, ["TIE_SLAVE", "SLAVE_TIE", "TIE_SLAV", "SLAVE_TI", "tie_slave"]))
            if not master_nodes and any(name in existing for name in ("TIE_MASTER", "MASTER_TIE", "TIE_MAST", "MASTER_T")):
                master_nodes.update(self._get_component_node_ids(mapdl, ["TIE_MASTER", "MASTER_TIE", "TIE_MAST", "MASTER_T", "tie_master"]))
            # 이름이 정형화되지 않은 경우 키워드 매칭으로 추가 보강
            if not slave_nodes:
                slave_nodes.update(self._get_component_node_ids_by_keywords(mapdl, include=("SLAVE", "TIE")))
            if not master_nodes:
                master_nodes.update(self._get_component_node_ids_by_keywords(mapdl, include=("MASTER", "TIE")))
            if slave_nodes or master_nodes:
                self._log(
                    f"  Fallback components: slave_nodes={len(slave_nodes)} "
                    f"master_nodes={len(master_nodes)}"
                )

        created_cms = set()

        # ── 2) 노드 리스트로부터 CM 생성 (매크로로 NSEL,A 일괄 처리) ──
        if slave_nodes and self._create_cm_from_node_list(mapdl, "TIE_SLAVE", slave_nodes, as_elements=True):
            created_cms.add("TIE_SLAVE")
            self._log(f"  Created CM TIE_SLAVE ({len(slave_nodes)} nodes -> ELEM component)")
        if master_nodes and self._create_cm_from_node_list(mapdl, "TIE_MASTER", master_nodes, as_elements=True):
            created_cms.add("TIE_MASTER")
            self._log(f"  Created CM TIE_MASTER ({len(master_nodes)} nodes -> ELEM component)")

        # CE 기반 slave 노드가 파일럿 노드인 경우 ESLN 결과가 0개일 수 있다.
        # 이때는 기존 slave/tie 성분에서 element 기반으로 재구성 시도.
        tie_slave_eids = self._get_component_element_ids(mapdl, ["TIE_SLAVE"])
        if not tie_slave_eids:
            alt_slave_eids = self._get_component_element_ids_by_keywords(mapdl, include=("SLAVE", "TIE"))
            if alt_slave_eids and self._create_cm_from_element_list(mapdl, "TIE_SLAVE", alt_slave_eids):
                created_cms.add("TIE_SLAVE")
                self._log(
                    f"  Rebuilt CM TIE_SLAVE from existing element component "
                    f"({len(alt_slave_eids)} elements)"
                )

        mapdl.allsel("ALL")

        # ── 3) 보존 대상(TIE_SLAVE/TIE_MASTER)을 제외한 나머지 CM 네이밍 삭제 ──
        # CMDELE은 컴포넌트 "이름(별칭)"만 제거하며, 묶여 있던 노드/요소
        # 자체는 그대로 두기 때문에 모델 구조에는 영향이 없다.
        existing_cms = self._list_all_components(mapdl)
        deleted_cm = 0
        for name in existing_cms:
            if name.upper() in created_cms:
                continue
            up = name.upper()
            # 기존 tie 관련 컴포넌트는 보존 (이름이 다르면 후속 파싱에서 필요할 수 있음)
            if ("TIE" in up and "SLAVE" in up) or ("TIE" in up and "MASTER" in up):
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
            # e.g. "  12345 UX 1.0000E+00"
            re.compile(r"^\s*(\d+)\s+(UX|UY|UZ|ROTX|ROTY|ROTZ|TEMP)\s+[-+0-9.Ee]+", re.IGNORECASE),
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

    def _create_cm_from_node_list(self, mapdl, cm_name, nodes, as_elements=False):
        """Select node numbers and save component as NODE or ELEM.

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
                if as_elements:
                    f.write("ESLN,S\n")
                    f.write(f"CM,{cm_name},ELEM\n")
                else:
                    f.write(f"CM,{cm_name},NODE\n")
                f.write("ALLSEL,ALL\n")
            mapdl.input(macro_path)
            return True
        except Exception as e:
            self._log(f"  Warning: failed to create {cm_name}: {e}")
            return False

    def _create_cm_from_element_list(self, mapdl, cm_name, elems):
        """Select element numbers and save component as ELEM."""
        if not elems:
            return False
        macro_path = os.path.join(mapdl.directory, f"_mkcm_elem_{cm_name}.mac")
        try:
            with open(macro_path, "w") as f:
                f.write("ALLSEL,ALL\n")
                f.write("ESEL,NONE\n")
                for eid in sorted(elems):
                    f.write(f"ESEL,A,ELEM,,{eid}\n")
                f.write(f"CM,{cm_name},ELEM\n")
                f.write("ALLSEL,ALL\n")
            mapdl.input(macro_path)
            return True
        except Exception as e:
            self._log(f"  Warning: failed to create {cm_name} from elements: {e}")
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

        self._log(f"  Deleted {deleted} / {len(all_mats)} unused material(s).")

    def _expand_etblock(self, cdb_path):
        """Replace every ETBLOCK block in a .cdb with ET/KEYOPT cards.

        The ETBLOCK command was introduced in Ansys 2023 R1 as a compact
        replacement for sequences of ET + KEYOPT commands. Tools that
        still parse the classic CDB dialect (notably `abaqus fromansys`
        and older HyperMesh versions) reject it with messages like
        "unrecognized keyword = ETBLOCK" or "found 0 entries in ET data".

        The block format emitted by MAPDL is:

            ETBLOCK,<numhead>,<maxkyo>
            (i9,19a9)
                    1      186        0        0 ...
                    2      174        0        0 ...
                   -1

        Each data row is: itype, ename, kop1, kop2, ..., kop18 (trailing
        zero fields may be truncated). We rewrite the block as:

            ET,<itype>,<ename>
            KEYOPT,<itype>,<n>,<value>     (only for non-zero keyopts)

        The file is rewritten in place. Returns the number of expanded
        element-type rows, or 0 if no ETBLOCK section was found.
        """
        try:
            with open(cdb_path, "r") as f:
                lines = f.readlines()
        except (FileNotFoundError, OSError):
            return 0

        out_lines = []
        expanded = 0
        i = 0
        n = len(lines)
        while i < n:
            line = lines[i]
            if line.lstrip().upper().startswith("ETBLOCK"):
                # Skip the ETBLOCK header and its (i9,19a9)-style format line.
                i += 1
                if i < n and lines[i].lstrip().startswith("("):
                    i += 1
                # Consume data rows until a lone "-1" sentinel.
                while i < n:
                    row = lines[i].strip()
                    if not row:
                        i += 1
                        continue
                    if row.startswith("-1"):
                        i += 1
                        break
                    parts = row.split()
                    try:
                        itype = int(parts[0])
                        ename = parts[1]
                        keyopts = [int(p) for p in parts[2:]]
                    except (ValueError, IndexError):
                        # Unrecognised row — keep it verbatim to be safe.
                        out_lines.append(lines[i])
                        i += 1
                        continue
                    # ET accepts the element name plus up to 6 positional
                    # keyopts (KOP1..KOP6). Inline those so downstream
                    # tools like `abaqus fromansys` that do not recognise
                    # the standalone KEYOPT command still see them. Only
                    # the rarely-used keyopts 7..18 remain as separate
                    # KEYOPT lines.
                    inline_kops = keyopts[:6]
                    while inline_kops and inline_kops[-1] == 0:
                        inline_kops.pop()
                    et_line = f"ET,{itype},{ename}"
                    if inline_kops:
                        et_line += "," + ",".join(str(k) for k in inline_kops)
                    out_lines.append(et_line + "\n")
                    for extra_idx in range(6, len(keyopts)):
                        kop = keyopts[extra_idx]
                        if kop != 0:
                            out_lines.append(
                                f"KEYOPT,{itype},{extra_idx + 1},{kop}\n"
                            )
                    expanded += 1
                    i += 1
                continue
            out_lines.append(line)
            i += 1

        if expanded:
            with open(cdb_path, "w") as f:
                f.writelines(out_lines)
        return expanded

    # Subset of MAPDL material property labels that might appear in MP /
    # MPDATA commands. Used to detect whether a line is in the blocked
    # "version-tagged" form (the property label sits at position 3) or
    # in the classic form (label at position 1).
    _MP_LABELS = frozenset({
        "EX", "EY", "EZ", "GXY", "GYZ", "GXZ",
        "NUXY", "NUYZ", "NUXZ", "PRXY", "PRYZ", "PRXZ",
        "DENS", "ALPX", "ALPY", "ALPZ", "CTEX", "CTEY", "CTEZ",
        "KXX", "KYY", "KZZ", "C", "ENTH", "HF", "EMIS",
        "VISC", "SONC", "MU", "DMPR", "DMPS",
        "MURX", "MURY", "MURZ", "MGXX", "MGYY", "MGZZ",
        "RSVX", "RSVY", "RSVZ", "PERX", "PERY", "PERZ",
        "LSST", "BETD", "REFT",
    })

    def _rewrite_mp_mpdata_to_classic(self, cdb_path):
        """Convert MP / MPDATA lines back to the classic comma-separated
        form that `abaqus fromansys` understands.

        Modern MAPDL CDWRITE (BLOCKED) emits material commands with a
        release/version tag inserted before the material number:

            MPDATA,R5.0, 1,EX  ,         0, 2.10000000000E+11,
            MP    ,R5.0, 1,DENS,  7.85000E+03

        abaqus fromansys, however, parses the classic grammar where the
        property label sits right after the command:

            MPDATA,EX,1,0,2.10000000000E+11
            MP,DENS,1,7.85E+03

        When fromansys reads the blocked form it treats the version tag
        ("R5.0" or similar) as the label, emits hundreds of
        "Material Property <tag> not supported" warnings, and the
        resulting .inp has no materials at all.

        This rewriter walks each line and, for MP / MPDATA, checks
        whether the *third* whitespace/comma-separated token is a known
        MP label while the *first* token is not. In that case it
        reorders the fields into the classic form. Lines that already
        look classic, or that we cannot confidently identify, are
        passed through untouched so we do not corrupt unrelated data.
        The file is rewritten in place and the number of converted
        lines is returned.
        """
        try:
            with open(cdb_path, "r") as f:
                lines = f.readlines()
        except (FileNotFoundError, OSError):
            return 0

        def _split_csv(payload):
            return [tok.strip() for tok in payload.split(",")]

        changed = 0
        out_lines = []
        for line in lines:
            stripped = line.lstrip()
            upper = stripped.upper()
            matched_cmd = None
            for cmd in ("MPDATA", "MP"):
                if upper.startswith(cmd + ",") or upper.startswith(cmd + " "):
                    matched_cmd = cmd
                    break
                if upper.rstrip() == cmd:
                    matched_cmd = cmd
                    break
                # MAPDL pads command names with spaces (e.g. "MP    ,").
                head = upper[: len(cmd)]
                tail = upper[len(cmd) :].lstrip()
                if head == cmd and tail.startswith(","):
                    matched_cmd = cmd
                    break
            if matched_cmd is None:
                out_lines.append(line)
                continue

            # Split off the command, keep the rest as the argument list.
            comma = stripped.find(",")
            if comma < 0:
                out_lines.append(line)
                continue
            payload = stripped[comma + 1 :].rstrip("\n")
            tokens = _split_csv(payload)
            if len(tokens) < 3:
                out_lines.append(line)
                continue

            tok0_upper = tokens[0].upper()
            tok2_upper = tokens[2].upper() if len(tokens) > 2 else ""

            classic_ok = tok0_upper in self._MP_LABELS
            blocked_ok = (
                tok0_upper not in self._MP_LABELS
                and tok2_upper in self._MP_LABELS
            )

            if classic_ok or not blocked_ok:
                out_lines.append(line)
                continue

            # Blocked form detected: tokens = [tag, mat, lab, rest...]
            tag, mat, lab, *rest = tokens
            # Drop trailing empty fields that MAPDL likes to pad with.
            while rest and rest[-1] == "":
                rest.pop()
            new_tokens = [lab, mat, *rest]
            new_line = f"{matched_cmd}," + ",".join(new_tokens) + "\n"
            out_lines.append(new_line)
            changed += 1

        if changed:
            with open(cdb_path, "w") as f:
                f.writelines(out_lines)
        return changed

    def _step4_convert(self, cdb_path):
        """CDB를 직접 파싱해서 Abaqus INP 템플릿 생성"""
        self._log("\n=== Step 4: direct text INP build (no fromansys) ===")

        out_dir = self.output_dir.get()
        inp_path = os.path.join(out_dir, "converted_model.inp")

        nodes = self._parse_cdb_nodes(cdb_path)
        elems_by_mat = self._parse_cdb_elements_by_mat(cdb_path)
        nset_txt = os.path.join(out_dir, "step1_nsets.txt")
        mplist_txt = os.path.join(out_dir, "step1_mplist.txt")
        cdb_nsets = self._parse_cdb_nsets(cdb_path)
        if os.path.exists(nset_txt):
            nsets = self._read_nsets_txt(nset_txt)
            # step1_nsets에 일부가 비어있으면 CDB의 CMBLOCK(tie_master/tie_slave 등)으로 보강
            for k, vals in cdb_nsets.items():
                if not nsets.get(k):
                    nsets[k] = vals
        else:
            nsets = cdb_nsets
        mat_info = self._read_materials_from_mplist_txt(mplist_txt) if os.path.exists(mplist_txt) else {}
        mat_ids = sorted(mat_info.keys()) if mat_info else sorted(elems_by_mat.keys())

        if not nodes:
            raise RuntimeError("NBLOCK에서 노드를 읽지 못했습니다.")
        if not elems_by_mat:
            raise RuntimeError("EBLOCK에서 요소를 읽지 못했습니다.")

        # Abaqus 입력 전 길이 스케일 보정 (x1000)
        nodes = self._scale_nodes(nodes, 1000.0)
        self._log("Applied coordinate scale-up: x1000")

        self._write_template_inp(inp_path, nodes, elems_by_mat, mat_ids, nsets, mat_info)
        self._log(f"INP created: {inp_path}")
        self._log(
            "NOTE: 재료 상세(온도의존/ENG CONSTANTS/CTE)는 템플릿 자리만 생성됩니다. "
            "실제 값은 INP에서 채워주세요."
        )

    def _parse_cdb_nodes(self, cdb_path):
        """Parse NBLOCK and return {node_id: (x, y, z)}."""
        with open(cdb_path, "r") as f:
            lines = f.readlines()

        nodes = {}
        in_nblock = False
        skip_format = False
        num_pat = re.compile(r"[-+]?\d+(?:\.\d+)?(?:[Ee][-+]?\d+)?")
        int_pat = re.compile(r"[-+]?\d+")

        for raw in lines:
            s = raw.strip()
            u = s.upper()
            if not in_nblock and u.startswith("NBLOCK"):
                in_nblock = True
                skip_format = True
                continue
            if not in_nblock:
                continue
            if skip_format:
                skip_format = False
                continue
            if s.startswith("-1"):
                in_nblock = False
                continue
            if not s:
                continue

            ints = int_pat.findall(s)
            nums = num_pat.findall(s)
            if not ints or len(nums) < 4:
                continue
            try:
                nid = int(ints[0])
                x, y, z = float(nums[-3]), float(nums[-2]), float(nums[-1])
            except ValueError:
                continue
            nodes[nid] = (x, y, z)
        return nodes

    def _parse_cdb_elements_by_mat(self, cdb_path):
        """Parse EBLOCK and return {mat_id: [(eid, [n1..n8]), ...]}.

        NOTE: 이 파서는 SOLID C3D8 계열에 맞춘 간단 파서다.
        """
        with open(cdb_path, "r") as f:
            lines = f.readlines()

        elems_by_mat = defaultdict(list)
        in_eblock = False
        skip_format = False
        int_pat = re.compile(r"[-+]?\d+")

        for raw in lines:
            s = raw.strip()
            u = s.upper()
            if not in_eblock and u.startswith("EBLOCK"):
                in_eblock = True
                skip_format = True
                continue
            if not in_eblock:
                continue
            if skip_format:
                skip_format = False
                continue
            if s.startswith("-1"):
                in_eblock = False
                continue
            if not s:
                continue

            vals = [int(x) for x in int_pat.findall(s)]
            if len(vals) < 10:
                continue

            # 일반적인 SOLID EBLOCK 행 기준:
            # [MAT, TYPE, REAL, SEC, ESYS, ..., EID, N1..N8]
            mat_id = vals[0]
            eid = vals[-9]
            conn = vals[-8:]
            if len(conn) == 8:
                elems_by_mat[mat_id].append((eid, conn))
        return elems_by_mat

    def _parse_cdb_nsets(self, cdb_path):
        """Parse NODE CMBLOCKs and return {name_lower: [node_ids]}."""
        with open(cdb_path, "r") as f:
            lines = f.readlines()

        nsets = {}
        i = 0
        n = len(lines)
        int_pat = re.compile(r"[-+]?\d+")
        while i < n:
            line = lines[i].strip()
            if not line.upper().startswith("CMBLOCK"):
                i += 1
                continue

            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 3:
                i += 1
                continue
            name = parts[1]
            ent_type = parts[2].upper()
            i += 1
            if i < n and lines[i].lstrip().startswith("("):
                i += 1
            if ent_type != "NODE":
                while i < n and not lines[i].strip().startswith("-1"):
                    i += 1
                i += 1
                continue

            node_ids = []
            while i < n:
                s = lines[i].strip()
                if s.startswith("-1"):
                    i += 1
                    break
                if s:
                    node_ids.extend(int(x) for x in int_pat.findall(s) if int(x) > 0)
                i += 1
            if node_ids:
                nsets[name.lower()] = sorted(set(node_ids))
        return nsets

    def _read_nsets_txt(self, nset_path):
        nsets = {}
        cur = None
        int_pat = re.compile(r"[-+]?\d+")
        with open(nset_path, "r") as f:
            for raw in f:
                s = raw.strip()
                if not s:
                    continue
                if s.startswith("[") and s.endswith("]"):
                    cur = s[1:-1].strip().lower()
                    nsets[cur] = []
                    continue
                if cur is None:
                    continue
                for tok in int_pat.findall(s):
                    nsets[cur].append(int(tok))
        for k in list(nsets.keys()):
            nsets[k] = sorted(set(nsets[k]))
        return nsets

    def _read_materials_from_mplist_txt(self, mplist_path):
        """Parse MPLIST-like text tables with tabs/newlines/blank temps.

        Returns:
            {
              mat_id: {
                'name': 'mat{id}',
                'props': {
                  'ex': {'ref_temp': 183.0|None, 'rows': [(temp|None, value), ...]},
                  ...
                },
                'raw_lines': [...]
              }
            }
        """
        mats = {}
        cur_id = None
        cur_prop = None
        num_re = re.compile(r"[-+]?\d+(?:\.\d+)?(?:[Ee][-+]?\d+)?")

        def _to_float(tok):
            try:
                return float(tok)
            except ValueError:
                return None

        with open(mplist_path, "r") as f:
            for raw in f:
                line = raw.rstrip("\n")
                s = line.strip()
                if not s:
                    continue

                m = re.search(r"MATERIAL\s+NUMBER\s*=?\s*(\d+)", s, re.IGNORECASE)
                if m:
                    cur_id = int(m.group(1))
                    mats[cur_id] = {"name": f"mat{cur_id}", "raw_lines": [], "props": {}}
                    cur_prop = None
                    continue
                if cur_id is None:
                    continue
                mats[cur_id]["raw_lines"].append(line)

                # ex) "temp ex", "temp alpx reference temp.=183"
                if re.match(r"^\s*temp\b", s, re.IGNORECASE):
                    parts = s.split()
                    if len(parts) >= 2:
                        cur_prop = parts[1].strip().lower()
                        ref_match = re.search(r"reference\s*temp\.?\s*=\s*(" + num_re.pattern + ")", s, re.IGNORECASE)
                        ref_temp = float(ref_match.group(1)) if ref_match else None
                        mats[cur_id]["props"].setdefault(cur_prop, {"ref_temp": ref_temp, "rows": []})
                        if ref_temp is not None:
                            mats[cur_id]["props"][cur_prop]["ref_temp"] = ref_temp
                    continue

                if not cur_prop:
                    continue
                nums = re.findall(num_re, s)
                # 빈 temperature(상수값) 케이스: 값 1개만 있는 행
                if len(nums) == 1:
                    val = _to_float(nums[0])
                    if val is not None:
                        mats[cur_id]["props"][cur_prop]["rows"].append((None, val))
                    continue
                # 일반 케이스: temp + value
                t = _to_float(nums[0]) if len(nums) >= 1 else None
                v = _to_float(nums[1]) if len(nums) >= 2 else None
                if t is not None and v is not None:
                    mats[cur_id]["props"][cur_prop]["rows"].append((t, v))
        return mats

    def _fmt_num(self, v):
        if isinstance(v, (int, float)):
            return f"{v:.9g}"
        return str(v)

    def _scale_nodes(self, nodes, factor):
        """Return scaled node coordinates by the given factor."""
        if factor == 1.0:
            return nodes
        return {
            nid: (xyz[0] * factor, xyz[1] * factor, xyz[2] * factor)
            for nid, xyz in nodes.items()
        }

    def _prop_rows(self, props, key):
        entry = props.get(key, {})
        return entry.get("rows", [])

    def _value_for_temp(self, rows, temp):
        exact = [v for t, v in rows if t is not None and abs(t - temp) <= 1e-12]
        if exact:
            return exact[-1]
        consts = [v for t, v in rows if t is None]
        return consts[-1] if consts else None

    def _temps_from_rows(self, rows):
        return sorted({t for t, _ in rows if t is not None})

    def _write_template_inp(self, inp_path, nodes, elems_by_mat, mat_ids, nsets, mat_info):
        with open(inp_path, "w") as f:
            f.write("*NODE\n")
            for nid in sorted(nodes):
                x, y, z = nodes[nid]
                f.write(f"{nid}, {x:.9g}, {y:.9g}, {z:.9g}\n")

            for mid in mat_ids:
                es = f"eset{mid}"
                f.write(f"*ELEMENT,TYPE=C3D8I,ELSET={es}\n")
                for eid, conn in sorted(elems_by_mat.get(mid, []), key=lambda x: x[0]):
                    f.write(f"{eid}, " + ", ".join(str(n) for n in conn) + "\n")

            eff_mats = []
            for mid in mat_ids:
                es = f"eset{mid}"
                mat = mat_info.get(mid, {}).get("name", f"mat{mid}")
                if mat.lower().startswith("mat999"):
                    eff_mats.append((es, mat))
                else:
                    f.write(f"*SOLID SECTION, ELSET={es}, MATERIAL={mat}\n")

            if eff_mats:
                f.write("*Orientation, name=Ori-1\n")
                f.write("1,0,0,0,1,0\n")
                f.write("1,0\n")
                for es, mat in eff_mats:
                    f.write(f"*SOLID SECTION, ELSET={es}, orientation=Ori-1, MATERIAL={mat}\n")

            required_nsets = [
                "nset_temperature",
                "nset_bc_y",
                "nset_bc_x",
                "nset_bc_all",
            ]
            for ns in required_nsets:
                f.write(f"*NSET, NSET={ns}\n")
                ids = nsets.get(ns, [])
                for k in range(0, len(ids), 16):
                    f.write(", ".join(str(v) for v in ids[k:k + 16]) + "\n")
                if not ids:
                    f.write("** TODO: fill node IDs\n")

            master_eids = nsets.get("master_tie", []) or nsets.get("tie_master", [])
            slave_eids = nsets.get("slave_tie", []) or nsets.get("tie_slave", [])
            f.write("*ELSET, ELSET=master_tie\n")
            for k in range(0, len(master_eids), 16):
                f.write(", ".join(str(v) for v in master_eids[k:k + 16]) + "\n")
            if not master_eids:
                f.write("** TODO: fill element IDs\n")
            f.write("*ELSET, ELSET=slave_tie\n")
            for k in range(0, len(slave_eids), 16):
                f.write(", ".join(str(v) for v in slave_eids[k:k + 16]) + "\n")
            if not slave_eids:
                f.write("** TODO: fill element IDs\n")
            # Abaqus element surface는 ELSET 이름만으로는 부족하고 face ID(S1~S6)가 필요.
            # tie 면 방향 정보가 없는 템플릿 단계에서는 기본 face(S1)로 작성하고,
            # set이 비어 있으면 surface 자체를 생략해 경고를 피한다.
            if master_eids:
                f.write("*SURFACE, NAME=master_tie, TYPE=ELEMENT\n")
                f.write("master_tie, S1\n")
            else:
                f.write("** NOTE: master_tie surface skipped (empty element set)\n")
            if slave_eids:
                f.write("*SURFACE, NAME=slave_tie, TYPE=ELEMENT\n")
                f.write("slave_tie, S1\n")
            else:
                f.write("** NOTE: slave_tie surface skipped (empty element set)\n")

            for mid in mat_ids:
                mat = mat_info.get(mid, {}).get("name", f"mat{mid}")
                f.write(f"*MATERIAL, NAME={mat}\n")
                props = mat_info.get(mid, {}).get("props", {})
                if mat.lower().startswith("mat999"):
                    # Orthotropic
                    f.write("*ELASTIC, TYPE=ENGINEERING CONSTANTS\n")
                    keys_main = ["ex", "ey", "ez", "nuxy", "nuyz", "nuxz", "gxy", "gyz", "gxz"]
                    rows_all = []
                    for k in keys_main:
                        rows_all.extend(self._prop_rows(props, k))
                    temps = self._temps_from_rows(rows_all)
                    if temps:
                        for t in temps:
                            vals = [self._value_for_temp(self._prop_rows(props, k), t) for k in keys_main]
                            if any(v is None for v in vals):
                                continue
                            f.write(", ".join(self._fmt_num(v) for v in vals) + f", {self._fmt_num(t)}\n")
                    else:
                        vals = [self._value_for_temp(self._prop_rows(props, k), 0.0) for k in keys_main]
                        if any(v is None for v in vals):
                            f.write("** TODO: fill engineering constants\n")
                        else:
                            f.write(", ".join(self._fmt_num(v) for v in vals) + "\n")

                    f.write("*EXPANSION, TYPE=ORTHOTROPIC\n")
                    ctex_rows = self._prop_rows(props, "alpx")
                    ctey_rows = self._prop_rows(props, "alpy")
                    ctez_rows = self._prop_rows(props, "alpz")
                    cte_temps = self._temps_from_rows(ctex_rows + ctey_rows + ctez_rows)
                    if cte_temps:
                        for t in cte_temps:
                            vx = self._value_for_temp(ctex_rows, t)
                            vy = self._value_for_temp(ctey_rows, t)
                            vz = self._value_for_temp(ctez_rows, t)
                            if vx is None or vy is None or vz is None:
                                continue
                            f.write(f"{self._fmt_num(vx)}, {self._fmt_num(vy)}, {self._fmt_num(vz)}, {self._fmt_num(t)}\n")
                    else:
                        vx = self._value_for_temp(ctex_rows, 0.0)
                        vy = self._value_for_temp(ctey_rows, 0.0)
                        vz = self._value_for_temp(ctez_rows, 0.0)
                        if vx is None or vy is None or vz is None:
                            f.write("** TODO: fill orthotropic CTE\n")
                        else:
                            f.write(f"{self._fmt_num(vx)}, {self._fmt_num(vy)}, {self._fmt_num(vz)}\n")
                else:
                    # Isotropic
                    ex_rows = self._prop_rows(props, "ex")
                    nu_rows = self._prop_rows(props, "nuxy")
                    alpha_rows = self._prop_rows(props, "alpx")

                    elastic_temps = self._temps_from_rows(ex_rows + nu_rows)
                    if elastic_temps:
                        f.write("*ELASTIC\n")
                        for t in elastic_temps:
                            ex = self._value_for_temp(ex_rows, t)
                            nu = self._value_for_temp(nu_rows, t)
                            if ex is None or nu is None:
                                continue
                            f.write(f"{self._fmt_num(ex)}, {self._fmt_num(nu)}, {self._fmt_num(t)}\n")
                    else:
                        ex = self._value_for_temp(ex_rows, 0.0)
                        nu = self._value_for_temp(nu_rows, 0.0)
                        f.write("*ELASTIC\n")
                        if ex is None or nu is None:
                            f.write("** TODO: fill E, nu\n")
                        else:
                            f.write(f"{self._fmt_num(ex)}, {self._fmt_num(nu)}\n")

                    exp_temps = self._temps_from_rows(alpha_rows)
                    f.write("*EXPANSION\n")
                    if exp_temps:
                        for t in exp_temps:
                            a = self._value_for_temp(alpha_rows, t)
                            if a is not None:
                                f.write(f"{self._fmt_num(a)}, {self._fmt_num(t)}\n")
                    else:
                        a = self._value_for_temp(alpha_rows, 0.0)
                        if a is None:
                            f.write("** TODO: fill CTE\n")
                        else:
                            f.write(f"{self._fmt_num(a)}\n")

            f.write("*TIE, NAME=tie-1\n")
            f.write("master_tie, slave_tie\n")
            f.write("*INITIAL CONDITIONS, TYPE=TEMPERATURE\n")
            f.write("NSET_TEMPERATURE,183.0\n")
            f.write("*STEP, INC=10000, NAME=step, NLGEOM=NO\n")
            f.write("*STATIC\n")
            f.write("1.0, 1.0, 1.0e-15, 1.0\n")
            f.write("*TEMPERATURE, OP=NEW\n")
            f.write("NSET_TEMPERATURE, 25.0\n")
            f.write("*BOUNDARY\n")
            f.write("NSET_BC_Y,XSYMM\n")
            f.write("NSET_BC_X,YSYMM\n")
            f.write("NSET_BC_ALL,3,,0\n")


if __name__ == "__main__":
    root = tk.Tk()
    app = ConverterApp(root)
    root.mainloop()
