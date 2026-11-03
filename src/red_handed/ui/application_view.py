"""UC07 / FR8.1-3: a small executable picker, not a process explorer."""

import ntpath
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, ttk

from red_handed.core.applications import ApplicationSettings, ProtectedApplication


class ApplicationView(ttk.LabelFrame):
    def __init__(self, parent, get_settings, save_settings, *, on_change=None, on_saved=None, on_added=None):
        super().__init__(parent, text='Protected Applications', padding=8)
        self._get_settings, self._save_settings = get_settings, save_settings
        self._on_change = on_change or (lambda: None)
        self._on_saved = on_saved or (lambda: None)
        self._on_added = on_added or (lambda: None)
        self.save_error = None
        self.enabled = tk.BooleanVar(master=self)
        self.feedback = tk.StringVar(master=self)
        self.applications = []
        self.enable_button = ttk.Checkbutton(self, text='Restrict automatic protection to listed apps', variable=self.enabled)
        self.enable_button.grid(row=0, column=0, columnspan=2, sticky='w')
        self.listbox = tk.Listbox(self, height=4, width=64, exportselection=False)
        self.listbox.grid(row=1, column=0, sticky='ew', pady=4)
        self.columnconfigure(0, weight=1)
        controls = ttk.Frame(self)
        controls.grid(row=1, column=1, sticky='ns', padx=8)
        self.add_button = ttk.Button(controls, text='Add executable...', command=self.choose_application)
        self.add_button.pack(fill=tk.X)
        ttk.Button(controls, text='Remove', command=self.remove_selected).pack(fill=tk.X, pady=4)
        self.save_button = ttk.Button(self, text='Save Application Settings', command=self.save)
        self.save_button.grid(row=2, column=0, sticky='w')
        self.discard_button = ttk.Button(self, text='Discard changes', command=self.reload)
        self.discard_button.grid(row=2, column=1, sticky='w')
        ttk.Label(self, text='Protects the entire primary display, not individual windows.\n'
                  'An enabled empty list blocks automatic protection. Manual protection is independent.',
                  wraplength=650).grid(row=3, column=0, columnspan=2, sticky='w', pady=4)
        ttk.Label(self, textvariable=self.feedback, wraplength=650).grid(row=4, column=0, columnspan=2, sticky='w')
        self.reload()
        self.enabled.trace_add('write', lambda *_: self._on_change())

    @property
    def has_unsaved_changes(self):
        saved = self._get_settings()
        return self.enabled.get() != saved.application_aware_enabled or tuple(self.applications) != saved.protected_applications

    def _render(self):
        self.listbox.delete(0, tk.END)
        for app in self.applications:
            self.listbox.insert(tk.END, f'{app.display_name} - {app.executable_path}')

    def reload(self):
        settings = self._get_settings()
        self.enabled.set(settings.application_aware_enabled)
        self.applications = list(settings.protected_applications)
        self.feedback.set('')
        self._render()
        self.save_error = None
        self._on_change()

    def choose_application(self):
        path = filedialog.askopenfilename(parent=self, title='Select protected application executable',
                                          filetypes=[('Windows executable', '*.exe')])
        if path:
            try:
                if not Path(path).is_file():
                    raise ValueError('Select an existing executable file.')
                self.add_application(path)
            except (OSError, ValueError) as error:
                self.feedback.set(str(error))
                self._on_change()

    def add_application(self, path):
        app = ProtectedApplication(ntpath.basename(path), path)
        ApplicationSettings(self.enabled.get(), tuple([*self.applications, app]))
        self.applications.append(app)
        self._render()
        self.feedback.set('Unsaved changes. Select Save Application Settings to apply.')
        self._on_change()
        self._on_added()

    def remove_selected(self):
        selection = self.listbox.curselection()
        if selection:
            self.applications.pop(selection[0])
            self._render()
            self.feedback.set('Unsaved changes. Select Save Application Settings to apply.')
            self._on_change()

    def save(self):
        try:
            self._save_settings(ApplicationSettings(self.enabled.get(), tuple(self.applications)))
        except (ValueError, OSError) as error:
            self.save_error = str(error)
            self.feedback.set(f'Not saved: {error}')
            self._on_change()
        else:
            self.save_error = None
            self.feedback.set('Protected applications and setting saved.')
            self._on_saved()
