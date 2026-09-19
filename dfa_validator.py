"""
PE01 - Strings and DFA
-----------------------
A desktop program (Tkinter GUI) that:
  1. Loads a DFA transition table from a .dfa file.
  2. Loads a set of input strings from a .in file.
  3. Validates each string against the loaded DFA.
  4. Displays results on screen and writes them to a .out file.

Structured into two layers:
  - DFA / DFAParser  : pure logic, no UI dependency (easy to unit test)
  - DFAApp            : Tkinter UI that wires buttons/displays to the logic

Run with:  python dfa_validator.py
"""

import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox


# ---------------------------------------------------------------------------
# CORE LOGIC LAYER
# ---------------------------------------------------------------------------

class DFAFormatError(Exception):
    """Raised when a .dfa file does not follow the required specification."""
    pass


class DFA:
    """
    In-memory representation of a Deterministic Finite Automaton whose
    alphabet has exactly two symbols and whose states are single
    uppercase letters (A-Z).
    """

    def __init__(self, alphabet, transitions, start_state, final_states):
        self.alphabet = alphabet                # tuple of 2 symbols, e.g. ('0', '1')
        self.transitions = transitions          # dict: state -> {symbol: dest_state}
        self.start_state = start_state          # single state label
        self.final_states = final_states        # set of state labels

    @property
    def states(self):
        return set(self.transitions.keys())

    def run(self, input_string):
        """
        Simulate the DFA on input_string.
        Returns True (VALID) if the string is accepted, False (INVALID) otherwise.
        Any symbol not in the alphabet immediately makes the string INVALID,
        since no transition is defined for it.
        """
        current_state = self.start_state
        for ch in input_string:
            if ch not in self.alphabet:
                return False
            row = self.transitions.get(current_state)
            if row is None or ch not in row:
                return False
            current_state = row[ch]
        return current_state in self.final_states


class DFAParser:
    """Parses and validates a .dfa file into a DFA object."""

    VALID_TYPES = ("-", "+", "")

    @staticmethod
    def parse(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            raw_lines = [line.rstrip("\n").rstrip("\r") for line in f.readlines()]

        # Drop fully blank trailing lines, but keep interior structure intact.
        lines = [ln for ln in raw_lines if ln.strip() != ""]

        if len(lines) < 2:
            raise DFAFormatError("File is empty or missing the transition rows.")

        # ---- Line 1: alphabet ----
        alphabet_parts = [p.strip() for p in lines[0].split(",")]
        if len(alphabet_parts) != 2 or any(p == "" for p in alphabet_parts):
            raise DFAFormatError("The alphabet line must contain exactly two symbols.")
        if alphabet_parts[0] == alphabet_parts[1]:
            raise DFAFormatError("The two alphabet symbols must be unique.")
        alphabet = tuple(alphabet_parts)

        # ---- Remaining lines: state rows ----
        transitions = {}
        start_state = None
        final_states = set()
        seen_states = set()

        for idx, line in enumerate(lines[1:], start=2):
            fields = [p.strip() for p in line.split(",")]
            if len(fields) != 4:
                raise DFAFormatError(
                    f"Line {idx}: expected 4 comma-separated fields, got {len(fields)}."
                )

            type_flag, state, dest0, dest1 = fields

            if type_flag not in DFAParser.VALID_TYPES:
                raise DFAFormatError(
                    f"Line {idx}: type must be '-', '+', or blank (got '{type_flag}')."
                )
            if not DFAParser._is_state_label(state):
                raise DFAFormatError(f"Line {idx}: state '{state}' must be a single uppercase letter A-Z.")
            if not DFAParser._is_state_label(dest0) or not DFAParser._is_state_label(dest1):
                raise DFAFormatError(f"Line {idx}: destination states must be single uppercase letters A-Z.")
            if state in seen_states:
                raise DFAFormatError(f"Line {idx}: state '{state}' is defined more than once.")
            seen_states.add(state)

            transitions[state] = {alphabet[0]: dest0, alphabet[1]: dest1}

            if type_flag == "-":
                if start_state is not None:
                    raise DFAFormatError("There must be exactly one start state; found more than one.")
                start_state = state
            elif type_flag == "+":
                final_states.add(state)

        if start_state is None:
            raise DFAFormatError("No start state was specified (expected exactly one '-' row).")

        # Every destination referenced must be a state that was actually defined.
        for state, row in transitions.items():
            for sym, dest in row.items():
                if dest not in seen_states:
                    raise DFAFormatError(
                        f"State '{state}' transitions to undefined state '{dest}' on symbol '{sym}'."
                    )

        return DFA(alphabet, transitions, start_state, final_states)

    @staticmethod
    def _is_state_label(label):
        return len(label) == 1 and label.isalpha() and label.isupper()


def load_input_strings(filepath):
    """Loads a .in file as a list of strings, one per line (kept verbatim, any content allowed)."""
    with open(filepath, "r", encoding="utf-8") as f:
        lines = [line.rstrip("\n").rstrip("\r") for line in f.readlines()]
    # Drop only a trailing empty line caused by a final newline character.
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def write_output_file(in_filepath, results):
    """Writes VALID/INVALID results to a .out file with the same name/location as the .in file."""
    base, _ext = os.path.splitext(in_filepath)
    out_path = base + ".out"
    with open(out_path, "w", encoding="utf-8") as f:
        for line in results:
            f.write(line + "\n")
    return out_path


# ---------------------------------------------------------------------------
# UI LAYER
# ---------------------------------------------------------------------------

class DFAApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("PE01 - Strings and DFA")
        self.geometry("900x600")
        self.minsize(760, 520)

        # State kept by the app
        self.dfa = None                 # last SUCCESSFULLY loaded DFA
        self.dfa_filename = None        # name of the last successfully loaded .dfa file
        self.input_lines = []           # strings loaded from the .in file
        self.input_filepath = None      # full path of the currently loaded .in file

        self._build_ui()

    # ---------------- UI construction ----------------

    def _build_ui(self):
        toolbar = ttk.Frame(self, padding=8)
        toolbar.pack(side="top", fill="x")

        ttk.Button(toolbar, text="Load File", command=self.on_load_file).pack(side="left", padx=(0, 8))
        self.process_btn = ttk.Button(toolbar, text="Process", command=self.on_process, state="disabled")
        self.process_btn.pack(side="left")

        main_area = ttk.Frame(self, padding=(8, 0, 8, 8))
        main_area.pack(side="top", fill="both", expand=True)
        main_area.columnconfigure(0, weight=1)
        main_area.columnconfigure(1, weight=1)
        main_area.rowconfigure(0, weight=1)

        # --- Transition table (left) ---
        table_frame = ttk.LabelFrame(main_area, text="Transition table", padding=6)
        table_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 6))

        self.table = ttk.Treeview(table_frame, columns=("state", "sym0", "sym1"), show="headings", height=10)
        self.table.heading("state", text="State")
        self.table.heading("sym0", text="0")
        self.table.heading("sym1", text="1")
        self.table.column("state", width=90, anchor="center")
        self.table.column("sym0", width=90, anchor="center")
        self.table.column("sym1", width=90, anchor="center")
        self.table.pack(fill="both", expand=True)

        # --- Input / Output (right) ---
        io_frame = ttk.Frame(main_area)
        io_frame.grid(row=0, column=1, sticky="nsew")
        io_frame.rowconfigure(0, weight=1)
        io_frame.rowconfigure(1, weight=1)
        io_frame.columnconfigure(0, weight=1)

        input_frame = ttk.LabelFrame(io_frame, text="Input", padding=6)
        input_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 6))
        self.input_text = tk.Text(input_frame, wrap="none", state="disabled")
        self.input_text.pack(fill="both", expand=True)

        output_frame = ttk.LabelFrame(io_frame, text="Output", padding=6)
        output_frame.grid(row=1, column=0, sticky="nsew")
        self.output_text = tk.Text(output_frame, wrap="none", state="disabled")
        self.output_text.pack(fill="both", expand=True)

        # --- Status bar ---
        status_frame = ttk.Frame(self, padding=(8, 4))
        status_frame.pack(side="bottom", fill="x")
        self.status_var = tk.StringVar(value="Ready. Load a .dfa file and a .in file to begin.")
        ttk.Label(status_frame, textvariable=self.status_var, anchor="w").pack(fill="x")

    # ---------------- Button handlers ----------------

    def on_load_file(self):
        filepath = filedialog.askopenfilename(
            title="Select a .in or .dfa file",
            filetypes=[("Supported files", "*.in *.dfa"), ("All files", "*.*")],
        )
        if not filepath:
            return

        ext = os.path.splitext(filepath)[1].lower()
        filename = os.path.basename(filepath)

        if ext == ".in":
            self._load_input_file(filepath, filename)
        elif ext == ".dfa":
            self._load_dfa_file(filepath, filename)
        else:
            messagebox.showerror(
                "Unsupported file",
                "Only .in (input strings) and .dfa (transition table) files are supported.",
            )
            return

        self._refresh_process_button()

    def _load_input_file(self, filepath, filename):
        # Spec: "The program should load any .in file regardless of its content."
        try:
            self.input_lines = load_input_strings(filepath)
            self.input_filepath = filepath
            self._render_input()
            self._clear_output()
            self.status_var.set(f"Input from {filename} has been successfully loaded.")
        except Exception as exc:
            messagebox.showerror("Error loading input file", str(exc))
            self.status_var.set(f"Unable to load content from {filename}.")

    def _load_dfa_file(self, filepath, filename):
        try:
            new_dfa = DFAParser.parse(filepath)
            self.dfa = new_dfa
            self.dfa_filename = filename
            self._render_table()
            self.status_var.set(f"DFA table from {filename} has been successfully loaded.")
        except DFAFormatError as exc:
            if self.dfa is not None:
                self.status_var.set(
                    f"Unable to load content from {filename} due to invalid content. "
                    f"The program will be using the content from the most recently "
                    f"successfully loaded {self.dfa_filename}."
                )
            else:
                self.status_var.set(f"Unable to load content from {filename} due to invalid content.")
            messagebox.showerror("Invalid DFA file", str(exc))

    def on_process(self):
        if self.dfa is None or not self.input_filepath:
            return

        results = []
        for line in self.input_lines:
            verdict = "VALID" if self.dfa.run(line) else "INVALID"
            results.append(verdict)

        self._render_output(results)
        out_path = write_output_file(self.input_filepath, results)
        out_name = os.path.basename(out_path)
        in_name = os.path.basename(self.input_filepath)
        self.status_var.set(
            f"Input from {in_name} successfully processed using DFA table "
            f"from {self.dfa_filename}. Output saved to {out_name}."
        )

    # ---------------- Rendering helpers ----------------

    def _render_table(self):
        for row in self.table.get_children():
            self.table.delete(row)

        self.table.heading("sym0", text=self.dfa.alphabet[0])
        self.table.heading("sym1", text=self.dfa.alphabet[1])

        for state in sorted(self.dfa.transitions.keys()):
            row = self.dfa.transitions[state]
            if state == self.dfa.start_state:
                label = f"- {state}"
            elif state in self.dfa.final_states:
                label = f"+ {state}"
            else:
                label = state
            self.table.insert("", "end", values=(label, row[self.dfa.alphabet[0]], row[self.dfa.alphabet[1]]))

    def _render_input(self):
        self.input_text.configure(state="normal")
        self.input_text.delete("1.0", "end")
        self.input_text.insert("1.0", "\n".join(self.input_lines))
        self.input_text.configure(state="disabled")

    def _render_output(self, results):
        self.output_text.configure(state="normal")
        self.output_text.delete("1.0", "end")
        self.output_text.insert("1.0", "\n".join(results))
        self.output_text.configure(state="disabled")

    def _clear_output(self):
        self.output_text.configure(state="normal")
        self.output_text.delete("1.0", "end")
        self.output_text.configure(state="disabled")

    def _refresh_process_button(self):
        can_process = self.dfa is not None and bool(self.input_filepath)
        self.process_btn.configure(state=("normal" if can_process else "disabled"))


if __name__ == "__main__":
    app = DFAApp()
    app.mainloop()
