"""UC07 / FR8.1-3: a small executable picker, not a process explorer."""

import ntpath
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, ttk

from red_handed.core.applications import ApplicationSettings, ProtectedApplication


class ApplicationView(ttk.LabelFrame):
    def __init__(self, parent, get_settings, save_settings):
        super().__init__(parent, text='Protected Applications', padding=8)
        self._get_settings, self._save_settings = get_settings, save_settings
        self.enabled = tk.BooleanVar(master=self)
        self.feedback = tk.StringVar(master=self)
        self.applications = []
        ttk.Checkbutton(self, text='Enable application-aware protection', variable=self.enabled).grid(row=0, column=0, columnspan=2, sticky='w')
        self.listbox = tk.Listbox(self, height=4, width=64, exportselection=False)
        self.listbox.grid(row=1, column=0, sticky='ew', pady=4)
        self.columnconfigure(0, weight=1)
        controls = ttk.Frame(self)
        controls.grid(row=1, column=1, sticky='ns', padx=8)
        ttk.Button(controls, text='Add executable...', command=self.choose_application).pack(fill=tk.X)
        ttk.Button(controls, text='Remove', command=self.remove_selected).pack(fill=tk.X, pady=4)
        self.save_button = ttk.Button(self, text='Save Application Settings', command=self.save)
        self.save_button.grid(row=2, column=0, sticky='w')
        ttk.Label(self, text='Protects the entire primary display, not individual windows.\n'
                  'Matches the full executable path. Unavailable detection blocks automatic protection only.',
                  wraplength=650).grid(row=3, column=0, columnspan=2, sticky='w', pady=4)
        ttk.Label(self, textvariable=self.feedback, wraplength=650).grid(row=4, column=0, columnspan=2, sticky='w')
        self.reload()

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

    def add_application(self, path):
        app = ProtectedApplication(ntpath.basename(path), path)
        ApplicationSettings(self.enabled.get(), tuple([*self.applications, app]))
        self.applications.append(app)
        self._render()
        self.feedback.set('Unsaved changes. Select Save Application Settings to apply.')

    def remove_selected(self):
        selection = self.listbox.curselection()
        if selection:
            self.applications.pop(selection[0])
            self._render()
            self.feedback.set('Unsaved changes. Select Save Application Settings to apply.')

    def save(self):
        try:
            self._save_settings(ApplicationSettings(self.enabled.get(), tuple(self.applications)))
        except (ValueError, OSError) as error:
            self.feedback.set(f'Not saved: {error}')
        else:
            self.feedback.set('Protected applications and setting saved.')
