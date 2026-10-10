# -*- coding: utf-8 -*-
# GARRY'S MOD 13 ADDON EDITOR
# FIX: truncamento inteligente de codigo antes de enviar pra IA
#      + contador de tokens + aviso proativo
# Bem provavel que tenha bugs por eu ser novo em python.

import os
import sys
import json
import shutil
import subprocess
import re
import threading
import zipfile
from datetime import datetime
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox, simpledialog
except ImportError:
    print("Tkinter nao encontrado!")
    input("Pressione Enter...")
    sys.exit(1)

try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    print("Groq nao instalado! AI desabilitado.")
    GROQ_AVAILABLE = False

try:
    from tkinterdnd2 import TkinterDnD
    DND_AVAILABLE = True
except ImportError:
    DND_AVAILABLE = False

try:
    from luaparser import ast as lua_ast
    LUAPARSER_AVAILABLE = True
except ImportError:
    LUAPARSER_AVAILABLE = False


# ==============================================
# FUNCOES AUXILIARES
# ==============================================

def get_base_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def get_default_projects_dir():
    try:
        return str(Path.home() / "Documents" / "GMod13Editor" / "projects")
    except Exception:
        return os.path.join(os.path.expanduser("~"), "GMod13Editor", "projects")


def get_plugins_dir():
    return os.path.join(get_base_dir(), "plugins")


def get_plugins_available_dir():
    return os.path.join(get_base_dir(), "plugins_available")


def get_snippets_dir():
    return os.path.join(get_base_dir(), "snippets")


def get_ai_history_file():
    return os.path.join(get_base_dir(), "ai_history.json")


def sanitize_name(name):
    if not name:
        return ""
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    name = name.strip().rstrip('.')
    reserved = {
        'con', 'prn', 'aux', 'nul',
        'com1', 'com2', 'com3', 'com4', 'com5', 'com6', 'com7', 'com8', 'com9',
        'lpt1', 'lpt2', 'lpt3', 'lpt4', 'lpt5', 'lpt6', 'lpt7', 'lpt8', 'lpt9'
    }
    if name.lower() in reserved:
        name = "_" + name
    return name


def truncate_filename(name, max_chars=20):
    if len(name) <= max_chars:
        return name
    ext = os.path.splitext(name)[1]
    base = name[:len(name) - len(ext)]
    keep = max_chars - len(ext) - 3
    if keep < 1:
        keep = 1
    return base[:keep] + "..." + ext


# ==============================================
# TRUNCATE INTELIGENTE
# ==============================================

class CodeTruncator:
    """Trunca codigo Lua de forma inteligente por linhas."""

    # Marcador que vai no meio
    MARKER = "\n-- ... [codigo truncado: {n} linhas removidas] ...\n"

    @classmethod
    def estimate_tokens(cls, text):
        """
        Estima tokens. Aproximacao: ~4 chars por token (padrao GPT).
        Para codigo pode ser ~3.5 chars/token.
        """
        if not text:
            return 0
        return int(len(text) / 3.8)

    @classmethod
    def truncate(cls, code, max_chars=16000, keep_top=True, keep_bottom=True):
        """
        Trunca mantendo topo + final.
        Retorna (codigo_truncado, foi_truncado, linhas_removidas).
        """
        if not code:
            return code, False, 0
        if len(code) <= max_chars:
            return code, False, 0

        lines = code.split('\n')
        total_lines = len(lines)

        # Reserva pra marcador
        marker_size = 80
        budget = max_chars - marker_size

        if keep_top and keep_bottom:
            half = budget // 2
            # Acumula linhas do topo
            top_lines = []
            top_size = 0
            for line in lines:
                if top_size + len(line) + 1 > half:
                    break
                top_lines.append(line)
                top_size += len(line) + 1

            # Acumula linhas do fim
            bot_lines = []
            bot_size = 0
            for line in reversed(lines):
                if bot_size + len(line) + 1 > half:
                    break
                bot_lines.insert(0, line)
                bot_size += len(line) + 1

            removed = total_lines - len(top_lines) - len(bot_lines)
            if removed < 0:
                removed = 0

            result = (
                '\n'.join(top_lines) +
                cls.MARKER.format(n=removed) +
                '\n'.join(bot_lines)
            )
            return result, True, removed

        elif keep_top:
            top_lines = []
            top_size = 0
            for line in lines:
                if top_size + len(line) + 1 > budget:
                    break
                top_lines.append(line)
                top_size += len(line) + 1
            removed = total_lines - len(top_lines)
            result = (
                '\n'.join(top_lines) +
                cls.MARKER.format(n=removed)
            )
            return result, True, removed

        else:
            bot_lines = []
            bot_size = 0
            for line in reversed(lines):
                if bot_size + len(line) + 1 > budget:
                    break
                bot_lines.insert(0, line)
                bot_size += len(line) + 1
            removed = total_lines - len(bot_lines)
            result = (
                cls.MARKER.format(n=removed) +
                '\n'.join(bot_lines)
            )
            return result, True, removed


# ==============================================
# CONSTANTES
# ==============================================

VERSION = "5.2.1"
AUTHOR = "Lixbot85"
CONFIG_FILE = "config.json"
CONFIG_FILE_LEGACY = "config.dat"
ICONS_DIR = "icons"
ICONS_DIR_DARK = "icons_dark"
LOGO_ICO = "logo.ico"
LOGO_PNG = "logo.png"
SPLASH_FILE = "splash.png"
SPLASH_DURATION_MS = 4000

MAX_TAB_WIDTH = 220

IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.tga', '.webp'}
AUDIO_EXTS = {'.wav', '.mp3', '.ogg', '.flac'}
MODEL_EXTS = {'.mdl', '.vvd', '.vtx', '.phy', '.vmt', '.vtf'}

LINT_DELAY_MS = 1200
SNIPPET_EXT = ".snippet.json"
MAX_AI_HISTORY = 30

# ===== LIMITES IA =====
AI_MAX_CODE_CHARS = 16000       # Tamanho maximo do codigo enviado
AI_WARN_THRESHOLD = 0.80        # Avisa se passar de 80% do limite
AI_MODEL_CONTEXT = 128000       # Tokens (contexto do gpt-oss-120b)


# ==============================================
# AI HISTORY MANAGER
# ==============================================

class AIHistoryManager:
    def __init__(self, history_file=None):
        self.history_file = history_file or get_ai_history_file()
        self.data = self._load()

    def _load(self):
        default = {"conversations": []}
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if not isinstance(data, dict):
                    return default
                if 'conversations' not in data:
                    data['conversations'] = []
                return data
            except Exception:
                return default
        return default

    def save(self):
        try:
            convs = self.data.get('conversations', [])
            if len(convs) > MAX_AI_HISTORY:
                convs = convs[-MAX_AI_HISTORY:]
                self.data['conversations'] = convs
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print("Erro historico IA: " + str(e))
            return False

    def new_conversation(self, title="Nova conversa"):
        conv = {
            "id": datetime.now().strftime("%Y%m%d_%H%M%S_%f"),
            "title": title,
            "created": datetime.now().isoformat(),
            "updated": datetime.now().isoformat(),
            "messages": [],
        }
        self.data['conversations'].append(conv)
        self.save()
        return conv

    def get_conversations(self):
        return list(self.data.get('conversations', []))

    def get_last(self):
        convs = self.get_conversations()
        if not convs:
            return None
        return convs[-1]

    def add_message(self, conv_id, role, content):
        for c in self.data.get('conversations', []):
            if c['id'] == conv_id:
                c['messages'].append({
                    "role": role, "content": content,
                    "time": datetime.now().isoformat(),
                })
                c['updated'] = datetime.now().isoformat()
                if role == 'user' and c['title'] == 'Nova conversa':
                    t = content.strip().split('\n')[0][:50]
                    if t:
                        c['title'] = t
                self.save()
                return True
        return False

    def delete_conversation(self, conv_id):
        self.data['conversations'] = [
            c for c in self.data.get('conversations', []) if c['id'] != conv_id
        ]
        self.save()

    def clear_all(self):
        self.data['conversations'] = []
        self.save()


# ==============================================
# GIT MANAGER
# ==============================================

class GitManager:
    def __init__(self, repo_path=None):
        self.repo_path = repo_path
        self.available = self._check_git()

    def _check_git(self):
        try:
            r = subprocess.run(["git", "--version"],
                               capture_output=True, text=True, timeout=5)
            return r.returncode == 0
        except Exception:
            return False

    def set_repo(self, path):
        self.repo_path = path

    def _run(self, args, timeout=30):
        if not self.repo_path:
            return False, "", "Sem repositorio."
        if not os.path.isdir(self.repo_path):
            return False, "", "Nao existe."
        try:
            r = subprocess.run(["git"] + args, cwd=self.repo_path,
                               capture_output=True, text=True, timeout=timeout)
            return r.returncode == 0, r.stdout, r.stderr
        except subprocess.TimeoutExpired:
            return False, "", "Timeout"
        except Exception as e:
            return False, "", str(e)

    def is_repo(self):
        ok, _, _ = self._run(["rev-parse", "--git-dir"])
        return ok

    def init(self): return self._run(["init"])
    def status(self): return self._run(["status", "--short"])
    def add_all(self): return self._run(["add", "-A"])
    def commit(self, message): return self._run(["commit", "-m", message])
    def push(self, remote="origin", branch="master"):
        return self._run(["push", "-u", remote, branch], timeout=120)
    def pull(self, remote="origin", branch="master"):
        return self._run(["pull", remote, branch], timeout=120)

    def current_branch(self):
        ok, out, _ = self._run(["rev-parse", "--abbrev-ref", "HEAD"])
        return out.strip() if ok else "master"

    def log_last(self, n=5):
        return self._run(["log", "--oneline", "-" + str(n)])


# ==============================================
# SNIPPET MANAGER
# ==============================================

class SnippetManager:
    def __init__(self, snippets_dir=None):
        self.snippets_dir = snippets_dir or get_snippets_dir()
        self.snippets = {}
        self._ensure_dir()

    def _ensure_dir(self):
        try:
            os.makedirs(self.snippets_dir, exist_ok=True)
        except Exception:
            pass

    def reload(self):
        self.snippets = {}
        if not os.path.isdir(self.snippets_dir):
            return
        try:
            for name in sorted(os.listdir(self.snippets_dir)):
                if not name.endswith(SNIPPET_EXT):
                    continue
                full = os.path.join(self.snippets_dir, name)
                try:
                    with open(full, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    sname = data.get('name', os.path.splitext(name)[0])
                    if sname:
                        self.snippets[sname] = {
                            'name': sname,
                            'code': data.get('code', ''),
                            'type': data.get('type', 'lua'),
                            'file': full,
                        }
                except Exception:
                    pass
        except Exception:
            pass

    def save(self, name, code, stype="lua"):
        name = sanitize_name(name)
        if not name:
            return False, "Nome invalido"
        fname = name.replace(' ', '_') + SNIPPET_EXT
        full = os.path.join(self.snippets_dir, fname)
        try:
            with open(full, 'w', encoding='utf-8') as f:
                json.dump({
                    "name": name, "code": code, "type": stype,
                    "created": datetime.now().isoformat()
                }, f, indent=2, ensure_ascii=False)
            self.reload()
            return True, full
        except Exception as e:
            return False, str(e)

    def delete(self, name):
        s = self.snippets.get(name)
        if not s:
            return False
        try:
            os.remove(s['file'])
            self.reload()
            return True
        except Exception:
            return False

    def get_all(self):
        return list(self.snippets.values())


# ==============================================
# LUA LINTER
# ==============================================

class LuaLinter:
    def __init__(self):
        self.available = LUAPARSER_AVAILABLE

    def check(self, code):
        if not self.available:
            return True, None, None
        if not code or not code.strip():
            return True, None, None
        try:
            lua_ast.parse(code)
            return True, None, None
        except Exception as e:
            msg = str(e)
            line = None
            m = re.search(r'\[line:\s*(\d+)\]', msg)
            if m:
                line = int(m.group(1))
            else:
                m = re.search(r'line\s+(\d+)', msg)
                if m:
                    line = int(m.group(1))
            msg_clean = msg.split('\n')[0]
            if len(msg_clean) > 200:
                msg_clean = msg_clean[:200] + "..."
            return False, line, msg_clean


# ==============================================
# LUA COMMON ERROR FIXER
# ==============================================

class LuaCommonFixes:
    RULES = [
        (r'\bif\s+([^\n=<>!]+?)\s*=\s*([^\n=<>!]+?)\s+then',
         r'if \1 == \2 then',
         'if x = 5 -> deveria ser =='),
        (r'\bwhile\s+([^\n=<>!]+?)\s*=\s*([^\n=<>!]+?)\s+do',
         r'while \1 == \2 do',
         'while x = 5 -> deveria ser =='),
        (r'\belseif\s+([^\n=<>!]+?)\s*=\s*([^\n=<>!]+?)\s+then',
         r'elseif \1 == \2 then',
         'elseif x = 5 -> deveria ser =='),
        (r'(?<![=!<>])=\s*~(?!=)', ' ~= ', '=~ -> deveria ser ~='),
        (r'\bend\s*;', 'end', 'end; -> removido ponto e virgula'),
        (r'\bprint\s+([^(])', r'print(\1', 'print x -> print(x'),
    ]

    @classmethod
    def find_issues(cls, code):
        issues = []
        if not code:
            return issues
        for i, line in enumerate(code.split('\n'), 1):
            if line.strip().startswith('--'):
                continue
            for pattern, replacement, desc in cls.RULES:
                if re.search(pattern, line):
                    try:
                        new_line = re.sub(pattern, replacement, line)
                    except Exception:
                        new_line = line
                    issues.append({
                        'line': i, 'desc': desc,
                        'old': line, 'new': new_line,
                    })
        return issues

    @classmethod
    def auto_fix(cls, code):
        if not code:
            return code, 0
        count = 0
        new_lines = []
        for line in code.split('\n'):
            if line.strip().startswith('--'):
                new_lines.append(line)
                continue
            new_line = line
            for pattern, replacement, desc in cls.RULES:
                try:
                    if re.search(pattern, new_line):
                        new_line = re.sub(pattern, replacement, new_line)
                        count += 1
                except Exception:
                    pass
            new_lines.append(new_line)
        return '\n'.join(new_lines), count


# ==============================================
# PLUGIN
# ==============================================

class Plugin:
    def __init__(self, folder_name, folder_path, metadata):
        self.folder_name = folder_name
        self.folder_path = folder_path
        self.metadata = metadata or {}
        self.loaded = True
        self.error = None

    @property
    def name(self): return self.metadata.get('name', self.folder_name)
    @property
    def version(self): return self.metadata.get('version', '0.0.0')
    @property
    def author(self): return self.metadata.get('author', 'desconhecido')
    @property
    def description(self): return self.metadata.get('description', '')
    @property
    def enabled(self): return bool(self.metadata.get('enabled', True))

    @property
    def requires(self):
        req = self.metadata.get('requires', [])
        if isinstance(req, list):
            return [str(x) for x in req]
        return []

    def set_enabled(self, value):
        self.metadata['enabled'] = bool(value)
        return self.save_metadata()

    def save_metadata(self):
        path = os.path.join(self.folder_path, "plugin.json")
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(self.metadata, f, indent=4, ensure_ascii=False)
            return True
        except Exception as e:
            print("Erro salvar plugin: " + str(e))
            return False

    def get_autocomplete(self):
        items = []
        for entry in self.metadata.get('autocomplete', []):
            try:
                if len(entry) >= 3:
                    items.append((str(entry[0]), str(entry[1]), str(entry[2])))
                elif len(entry) == 2:
                    items.append((str(entry[0]), str(entry[1]), ''))
                elif len(entry) == 1:
                    items.append((str(entry[0]), str(entry[0]), ''))
            except Exception:
                pass
        return items

    def get_keywords(self):
        items = []
        for entry in self.metadata.get('keywords', []):
            try:
                if len(entry) >= 2:
                    items.append((str(entry[0]), str(entry[1])))
                elif len(entry) == 1:
                    items.append((str(entry[0]), ''))
            except Exception:
                pass
        return items

    def get_templates(self):
        items = []
        for entry in self.metadata.get('templates', []):
            try:
                if not isinstance(entry, dict):
                    continue
                ttype = entry.get('type', '').lower()
                label = entry.get('label', '')
                script = entry.get('script', '')
                if not ttype or not label:
                    continue
                items.append({
                    'type': ttype, 'label': str(label),
                    'script': str(script), 'plugin': self.name,
                })
            except Exception:
                pass
        return items


class PluginManager:
    def __init__(self, plugins_dir=None, available_dir=None):
        self.plugins_dir = plugins_dir or get_plugins_dir()
        self.available_dir = available_dir or get_plugins_available_dir()
        self.plugins = {}
        self._ensure_dirs()
        self._create_available_examples()

    def _ensure_dirs(self):
        try:
            os.makedirs(self.plugins_dir, exist_ok=True)
        except Exception:
            pass
        try:
            os.makedirs(self.available_dir, exist_ok=True)
        except Exception:
            pass

    def _create_available_examples(self):
        try:
            existing = [d for d in os.listdir(self.available_dir)
                        if os.path.isdir(os.path.join(self.available_dir, d))
                        and not d.startswith('.')]
        except Exception:
            existing = []
        if existing:
            return
        self._write_available(
            "gmod_toolkit",
            {
                "name": "GMod Toolkit", "version": "1.0.0", "author": "Editor",
                "description": "Pacote oficial com 150+ auto-completes",
                "enabled": True, "requires": [],
                "autocomplete": [
                    ["surface.SetDrawColor", "surface.SetDrawColor(r, g, b, a)", "Cor"],
                    ["net.Start", "net.Start(\"nome\")", "NET"],
                    ["hook.Add", "hook.Add(evento, nome, fn)", "Hook"],
                    ["timer.Simple", "timer.Simple(t, fn)", "Timer"],
                    ["chat.AddText", "chat.AddText(Color(255,255,255), texto)", "Chat"],
                ],
                "keywords": [["ply", "Jogador"], ["ent", "Entidade"]],
                "templates": []
            }
        )
        self._write_available(
            "gmod_308_base",
            {
                "name": "308 Base (armas)", "version": "1.0.0", "author": "Editor",
                "description": "Templates da 308. REQUER GMod Toolkit.",
                "enabled": True, "requires": ["gmod_toolkit"],
                "autocomplete": [
                    ["SWEP.PA_Damage", "SWEP.PA_Damage = 20", "Dano"],
                ],
                "keywords": [],
                "templates": [{
                    "type": "swep", "label": "308 ModernWarfare",
                    "script": "--[[ {name} ]]\n\nSWEP.Base = \"weapon_308_base\"\nSWEP.PrintName = \"{name}\"\n"
                }]
            }
        )

    def _write_available(self, folder_name, metadata):
        full = os.path.join(self.available_dir, folder_name)
        try:
            os.makedirs(full, exist_ok=True)
            with open(os.path.join(full, "plugin.json"), 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=4, ensure_ascii=False)
            return True
        except Exception:
            return False

    def reload(self):
        self.plugins = {}
        if not os.path.isdir(self.plugins_dir):
            return
        try:
            entries = sorted(os.listdir(self.plugins_dir))
        except Exception:
            return
        for name in entries:
            full = os.path.join(self.plugins_dir, name)
            if not os.path.isdir(full):
                continue
            if name.startswith('.') or name.startswith('_'):
                continue
            meta_path = os.path.join(full, "plugin.json")
            if not os.path.exists(meta_path):
                continue
            try:
                with open(meta_path, 'r', encoding='utf-8') as f:
                    meta = json.load(f)
            except Exception as e:
                p = Plugin(name, full, {'name': name, 'enabled': False})
                p.loaded = False
                p.error = str(e)
                self.plugins[name] = p
                continue
            p = Plugin(name, full, meta)
            self.plugins[name] = p

    def _check_deps(self, plugin):
        missing = []
        for dep in plugin.requires:
            dep_plugin = self.plugins.get(dep)
            if dep_plugin is None:
                missing.append(dep)
            elif not dep_plugin.loaded:
                missing.append(dep + " (erro)")
            elif not dep_plugin.enabled:
                missing.append(dep + " (off)")
        return len(missing) == 0, missing

    def get_enabled(self):
        result = []
        for p in self.plugins.values():
            if not p.loaded or not p.enabled:
                continue
            ok, _ = self._check_deps(p)
            if ok:
                result.append(p)
        return result

    def get_all_autocomplete(self):
        items = []
        for p in self.get_enabled():
            items.extend(p.get_autocomplete())
        return items

    def get_all_keywords(self):
        items = []
        for p in self.get_enabled():
            items.extend(p.get_keywords())
        return items

    def get_templates_by_type(self, template_type):
        items = []
        for p in self.get_enabled():
            for t in p.get_templates():
                if t['type'] == template_type:
                    items.append(t)
        return items

    def list_available(self):
        items = []
        if not os.path.isdir(self.available_dir):
            return items
        try:
            entries = sorted(os.listdir(self.available_dir))
        except Exception:
            return items
        for name in entries:
            full = os.path.join(self.available_dir, name)
            if not os.path.isdir(full) or name.startswith('.') or name.startswith('_'):
                continue
            meta_path = os.path.join(full, "plugin.json")
            if not os.path.exists(meta_path):
                continue
            try:
                with open(meta_path, 'r', encoding='utf-8') as f:
                    meta = json.load(f)
            except Exception:
                continue
            installed = os.path.isdir(os.path.join(self.plugins_dir, name))
            items.append({
                'folder': name, 'meta': meta,
                'installed': installed, 'path': full,
            })
        return items

    def install_plugin(self, folder_name):
        src = os.path.join(self.available_dir, folder_name)
        dst = os.path.join(self.plugins_dir, folder_name)
        if not os.path.isdir(src):
            return False, "Origem nao existe."
        if os.path.exists(dst):
            return False, "Ja instalado."
        try:
            shutil.copytree(src, dst)
            return True, dst
        except Exception as e:
            return False, str(e)

    def uninstall_plugin(self, folder_name):
        dst = os.path.join(self.plugins_dir, folder_name)
        if not os.path.isdir(dst):
            return False, "Nao instalado."
        try:
            shutil.rmtree(dst)
            return True, folder_name
        except Exception as e:
            return False, str(e)


# ==============================================
# AUTOCOMPLETE - BASE DE DADOS
# ==============================================

LUA_KEYWORDS = [
    ("and", "Operador logico E"),
    ("break", "Sai do loop"),
    ("do", "Inicio de bloco"),
    ("else", "Senao"),
    ("elseif", "Senao se"),
    ("end", "Fim de bloco"),
    ("false", "Booleano falso"),
    ("for", "Loop for"),
    ("function", "Declara funcao"),
    ("if", "Condicional"),
    ("in", "Dentro de"),
    ("local", "Variavel local"),
    ("nil", "Valor nulo"),
    ("not", "Negacao"),
    ("or", "Operador logico OU"),
    ("repeat", "Repete ate"),
    ("return", "Retorna valor"),
    ("then", "Entao"),
    ("true", "Booleano verdadeiro"),
    ("until", "Ate"),
    ("while", "Enquanto"),
]

GMOD_GLOBALS = [
    ("print", "print(...)", "Imprime no console"),
    ("PrintTable", "PrintTable(tbl)", "Imprime tabela"),
    ("Msg", "Msg(texto)", "Console"),
    ("tostring", "tostring(v)", "Pra string"),
    ("tonumber", "tonumber(s)", "Pra numero"),
    ("type", "type(v)", "Tipo"),
    ("IsValid", "IsValid(obj)", "Verifica"),
    ("math.Rand", "math.Rand(min, max)", "Aleatorio"),
    ("math.random", "math.random(min, max)", "Aleatorio int"),
    ("string.format", "string.format(fmt, ...)", "Formata"),
    ("table.insert", "table.insert(t, v)", "Insere"),
    ("CurTime", "CurTime()", "Tempo"),
    ("timer.Simple", "timer.Simple(t, fn)", "Timer"),
    ("hook.Add", "hook.Add(evento, nome, fn)", "Hook"),
    ("ents.Create", "ents.Create(class)", "Entidade"),
    ("player.GetAll", "player.GetAll()", "Players"),
    ("util.Effect", "util.Effect(nome, data)", "Efeito"),
    ("Color", "Color(r, g, b, a)", "Cor"),
    ("Vector", "Vector(x, y, z)", "Vetor"),
    ("Angle", "Angle(p, y, r)", "Angulo"),
    ("Material", "Material(path)", "Material"),
    ("Sound", "Sound(path)", "Som"),
]

COMMON_METHODS = [
    ("GetPos", ":GetPos()", "Posicao"),
    ("SetPos", ":SetPos(v)", "Define posicao"),
    ("GetAngles", ":GetAngles()", "Angulos"),
    ("SetAngles", ":SetAngles(a)", "Define angulos"),
    ("GetModel", ":GetModel()", "Modelo"),
    ("SetModel", ":SetModel(m)", "Define modelo"),
    ("SetHealth", ":SetHealth(n)", "Define vida"),
    ("Remove", ":Remove()", "Remove"),
    ("IsPlayer", ":IsPlayer()", "Player?"),
    ("GetOwner", ":GetOwner()", "Dono"),
    ("EmitSound", ":EmitSound(som)", "Som"),
    ("ChatPrint", ":ChatPrint(msg)", "Chat"),
    ("Nick", ":Nick()", "Nome"),
    ("GetShootPos", ":GetShootPos()", "Posicao tiro"),
    ("GetAimVector", ":GetAimVector()", "Vetor mira"),
    ("ViewPunch", ":ViewPunch(a)", "Punch"),
    ("FireBullets", ":FireBullets(tbl)", "Balas"),
    ("SetHoldType", ":SetHoldType(t)", "Hold"),
]


# ==============================================
# TEMAS
# ==============================================

THEMES = {
    'dark': {
        'name': 'Escuro',
        'bg': '#1e1e1e', 'bg_alt': '#252526', 'bg_panel': '#2d2d2d',
        'fg': '#d4d4d4', 'fg_dim': '#858585', 'fg_bright': '#ffffff',
        'insert': '#ffffff', 'select_bg': '#264f78',
        'line_bg': '#252526', 'line_fg': '#858585',
        'comment': '#6a9955', 'string': '#ce9178', 'number': '#b5cea8',
        'keyword': '#569cd6',
        'tab_bg': '#2d2d2d', 'tab_bg_active': '#1e1e1e',
        'tab_fg': '#969696', 'tab_fg_active': '#ffffff',
        'icon_mode': 'dark', 'error_bg': '#5a1e1e',
    },
    'light': {
        'name': 'Claro',
        'bg': '#ffffff', 'bg_alt': '#f3f3f3', 'bg_panel': '#e8e8e8',
        'fg': '#1e1e1e', 'fg_dim': '#6a6a6a', 'fg_bright': '#000000',
        'insert': '#000000', 'select_bg': '#add6ff',
        'line_bg': '#f3f3f3', 'line_fg': '#a0a0a0',
        'comment': '#008000', 'string': '#a31515', 'number': '#098658',
        'keyword': '#0000ff',
        'tab_bg': '#e8e8e8', 'tab_bg_active': '#ffffff',
        'tab_fg': '#4a4a4a', 'tab_fg_active': '#000000',
        'icon_mode': 'light', 'error_bg': '#ffd0d0',
    },
}


# ==============================================
# AUTOCOMPLETE POPUP
# ==============================================

class AutoCompletePopup:
    def __init__(self, editor):
        self.editor = editor
        self.text_widget = None
        self.popup = None
        self.listbox = None
        self.items = []
        self.prefix_start = None

    def attach(self, text_widget):
        self.text_widget = text_widget
        text_widget.bind('<KeyRelease>', self._on_key, add="+")
        text_widget.bind('<Down>', self._on_down, add="+")
        text_widget.bind('<Up>', self._on_up, add="+")
        text_widget.bind('<Tab>', self._on_tab, add="+")
        text_widget.bind('<Return>', self._on_return, add="+")
        text_widget.bind('<Escape>', self._on_escape, add="+")
        text_widget.bind('<FocusOut>', lambda e: self.hide(), add="+")

    def detach(self, text_widget):
        self.hide()

    def _get_current_word(self):
        if not self.text_widget:
            return None, None
        try:
            cursor = self.text_widget.index(tk.INSERT)
            line_start = self.text_widget.index(cursor + " linestart")
            text_before = self.text_widget.get(line_start, cursor)
        except Exception:
            return None, None
        m = re.search(r'[A-Za-z_][\w\.]*$', text_before)
        if not m:
            return None, None
        word = m.group()
        return word, cursor + " -" + str(len(word)) + "c"

    def _build_items(self):
        items = []
        for kw, desc in LUA_KEYWORDS:
            items.append((kw, kw, desc))
        for name, sig, desc in GMOD_GLOBALS:
            items.append((name, name, desc + "  |  " + sig))
        for name, sig, desc in COMMON_METHODS:
            items.append((sig, sig, desc))
        try:
            pm = self.editor.plugin_manager
            for name, insertion, desc in pm.get_all_autocomplete():
                items.append((name, insertion, "[Plugin] " + desc))
            for kw, desc in pm.get_all_keywords():
                items.append((kw, kw, "[Plugin] " + desc))
        except Exception:
            pass
        return items

    def _on_key(self, event):
        if event.keysym in (
            'Up', 'Down', 'Left', 'Right', 'Home', 'End',
            'Prior', 'Next', 'Shift_L', 'Shift_R',
            'Control_L', 'Control_R', 'Alt_L', 'Alt_R',
            'Caps_Lock', 'Escape', 'Tab', 'Return',
        ):
            return
        if event.state & 0x4 or event.state & 0x8:
            return
        word, start_index = self._get_current_word()
        if not word:
            self.hide()
            return
        word_lower = word.lower()
        filtered = []
        for label, insertion, desc in self._build_items():
            if label.lower().startswith(word_lower):
                filtered.append((label, insertion, desc))
        filtered.sort(key=lambda x: (len(x[0]), x[0].lower()))
        filtered = filtered[:14]
        if not filtered:
            self.hide()
            return
        self.prefix_start = start_index
        self.show(filtered)

    def show(self, items):
        if not self.text_widget:
            return
        try:
            bbox = self.text_widget.bbox(tk.INSERT)
            if not bbox:
                self.hide()
                return
            x, y, w, h = bbox
            root_x = self.text_widget.winfo_rootx() + x
            root_y = self.text_widget.winfo_rooty() + y + h
        except Exception:
            return
        if self.popup is None:
            self.popup = tk.Toplevel(self.text_widget)
            self.popup.wm_overrideredirect(True)
            try:
                self.popup.attributes('-topmost', True)
            except Exception:
                pass
            self.listbox = tk.Listbox(
                self.popup, activestyle='none',
                font=('Consolas', 9), height=9, width=72,
                bg='#252526', fg='#d4d4d4',
                selectbackground='#094771', selectforeground='#ffffff',
                borderwidth=1, highlightthickness=1,
                highlightbackground='#3c3c3c', exportselection=False)
            self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            scroll = tk.Scrollbar(self.popup, orient=tk.VERTICAL,
                                   command=self.listbox.yview)
            scroll.pack(side=tk.RIGHT, fill=tk.Y)
            self.listbox.config(yscrollcommand=scroll.set)
            self.listbox.bind('<Double-Button-1>', lambda e: self.accept())
            self.listbox.bind('<ButtonRelease-1>', lambda e: self.accept())
        self.listbox.delete(0, tk.END)
        self.items = items
        for label, insertion, desc in items:
            d = desc if len(desc) <= 72 else desc[:69] + "..."
            self.listbox.insert(tk.END, "  " + label + "    " + d)
        if self.listbox.size() > 0:
            self.listbox.selection_clear(0, tk.END)
            self.listbox.selection_set(0)
            self.listbox.activate(0)
        try:
            self.popup.wm_geometry("+" + str(root_x) + "+" + str(root_y))
            self.popup.deiconify()
            self.popup.lift()
        except Exception:
            pass

    def hide(self):
        if self.popup:
            try:
                self.popup.withdraw()
            except Exception:
                pass
        self.prefix_start = None

    def is_visible(self):
        try:
            return self.popup is not None and self.popup.winfo_viewable()
        except Exception:
            return False

    def _on_down(self, event):
        if not self.is_visible():
            return None
        try:
            sel = self.listbox.curselection()
            if not sel:
                self.listbox.selection_set(0)
            else:
                i = min(sel[0] + 1, self.listbox.size() - 1)
                self.listbox.selection_clear(0, tk.END)
                self.listbox.selection_set(i)
                self.listbox.see(i)
        except Exception:
            pass
        return "break"

    def _on_up(self, event):
        if not self.is_visible():
            return None
        try:
            sel = self.listbox.curselection()
            if not sel:
                self.listbox.selection_set(0)
            else:
                i = max(sel[0] - 1, 0)
                self.listbox.selection_clear(0, tk.END)
                self.listbox.selection_set(i)
                self.listbox.see(i)
        except Exception:
            pass
        return "break"

    def _on_tab(self, event):
        if not self.is_visible():
            return None
        self.accept(); return "break"

    def _on_return(self, event):
        if not self.is_visible():
            return None
        self.accept(); return "break"

    def _on_escape(self, event):
        if self.is_visible():
            self.hide(); return "break"
        return None

    def accept(self):
        if not self.text_widget or not self.prefix_start:
            self.hide(); return
        try:
            sel = self.listbox.curselection()
            if not sel:
                self.hide(); return
            i = sel[0]
            if i >= len(self.items):
                self.hide(); return
            _, insertion, _ = self.items[i]
            cursor = self.text_widget.index(tk.INSERT)
            self.text_widget.delete(self.prefix_start, cursor)
            self.text_widget.insert(self.prefix_start, insertion)
        except Exception as e:
            print("autocomplete: " + str(e))
        self.hide()


# ==============================================
# ICON MANAGER
# ==============================================

class IconManager:
    FALLBACKS = {
        'folder': '\U0001F4C1', 'folder_open': '\U0001F4C2',
        'file_lua': '\U0001F4C4', 'file_txt': '\U0001F4CB',
        'file_img': '\U0001F5BC', 'file_mdl': '\U0001F9CA', 'file_snd': '\U0001F50A',
        'swep': '\U0001F52B', 'entity': '\U0001F4E6', 'ai': '\U0001F916',
        'save': '\U0001F4BE', 'compile': '\U0001F527', 'publish': '\U0001F4E4',
        'refresh': '\u27F3', 'search': '\U0001F50D', 'stats': '\U0001F4CA',
        'settings': '\u2699', 'about': '\u2139', 'new': '\u2728',
        'close': '\u274C', 'format': '\U0001F9F9', 'validate': '\U0001F9EA',
        'moon': '\U0001F319', 'plugin': '\U0001F50C',
        'git': '\U0001F33F', 'snippet': '\U0001F4CE',
        'market': '\U0001F6D2',
    }

    def __init__(self):
        self.cache = {}

    def _find(self, name, size, dark):
        base = ICONS_DIR_DARK if dark else ICONS_DIR
        for cand in (
            os.path.join(base, name + "_" + str(size) + ".png"),
            os.path.join(base, name + ".png"),
        ):
            if os.path.exists(cand):
                return cand
        if dark:
            return self._find(name, size, dark=False)
        return None

    def get(self, name, size=20, dark=False):
        if not PIL_AVAILABLE:
            return None
        key = (name, size, dark)
        if key in self.cache:
            return self.cache[key]
        path = self._find(name, size, dark)
        if not path:
            self.cache[key] = None
            return None
        try:
            img = Image.open(path).convert("RGBA")
            if img.width != size:
                img = img.resize((size, size), Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            self.cache[key] = photo
            return photo
        except Exception:
            self.cache[key] = None
            return None

    def clear(self):
        self.cache = {}


# ==============================================
# CONFIG
# ==============================================

class Config:
    def __init__(self):
        self.config_path = os.path.join(get_base_dir(), CONFIG_FILE)
        self.data = self.load()

    def get_defaults(self):
        return {
            'gmod_path': '',
            'output_path': str(Path.home() / "Documents" / "Garry's Mod AddonMaker" / "Output"),
            'groq_api_key': '', 'groq_model': 'openai/gpt-oss-120b',
            'window_width': 1400, 'window_height': 800,
            'last_project': '',
            'projects_dir': get_default_projects_dir(),
            'auto_save_enabled': True, 'auto_save_interval': 60,
            'font_size': 10, 'use_icons': True, 'theme': 'dark',
            'autocomplete_enabled': True, 'linter_enabled': True,
            'ai_beginner_mode': False,
            'ai_auto_truncate': True,
            'ai_max_chars': 16000,
            'git_remote': 'origin', 'git_branch': 'master',
            'version': VERSION,
        }

    def _migrate(self):
        legacy = os.path.join(get_base_dir(), CONFIG_FILE_LEGACY)
        d = self.get_defaults()
        if not os.path.exists(legacy):
            return d
        try:
            import pickle
            with open(legacy, 'rb') as f:
                old = pickle.load(f)
            for k in d:
                if k in old:
                    d[k] = old[k]
            try:
                shutil.copy2(legacy, legacy + ".v49.bak")
                os.remove(legacy)
            except Exception:
                pass
        except Exception:
            pass
        return d

    def load(self):
        d = self.get_defaults()
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                for k in d:
                    if k not in data:
                        data[k] = d[k]
                return data
            except Exception:
                return self._migrate()
        return self._migrate()

    def save(self):
        try:
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print("Erro config: " + str(e))
            return False

    def get(self, k, default=None): return self.data.get(k, default)
    def set(self, k, v): self.data[k] = v
    def __getitem__(self, k): return self.data.get(k)
    def __setitem__(self, k, v): self.data[k] = v


# ==============================================
# SPLASH
# ==============================================

class SplashScreen:
    def __init__(self, root, image_path, duration_ms=4000):
        self.root = root
        self.closed = False
        self._photo = None
        self.win = None
        if not PIL_AVAILABLE or not os.path.exists(image_path):
            self.closed = True
            return
        try:
            img = Image.open(image_path)
            max_w = int(root.winfo_screenwidth() * 0.5)
            max_h = int(root.winfo_screenheight() * 0.6)
            if img.width > max_w or img.height > max_h:
                ratio = min(max_w / img.width, max_h / img.height)
                img = img.resize((int(img.width * ratio), int(img.height * ratio)),
                                 Image.LANCZOS)
            self._photo = ImageTk.PhotoImage(img)
        except Exception:
            self.closed = True
            return
        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        try:
            self.win.attributes('-topmost', True)
        except Exception:
            pass
        w, h = self._photo.width(), self._photo.height()
        x = (root.winfo_screenwidth() - w) // 2
        y = (root.winfo_screenheight() - h) // 2
        self.win.geometry(str(w) + "x" + str(h) + "+" + str(x) + "+" + str(y))
        lbl = tk.Label(self.win, image=self._photo, borderwidth=0,
                       highlightthickness=0, bg='black')
        lbl.pack()
        self.win.bind("<Button-1>", lambda e: self.close())
        lbl.bind("<Button-1>", lambda e: self.close())
        self.win.bind("<Key>", lambda e: self.close())
        try:
            self.win.focus_force()
        except Exception:
            pass
        root.after(duration_ms, self.close)

    def close(self):
        if self.closed:
            return
        self.closed = True
        try:
            if self.win:
                self.win.destroy()
        except Exception:
            pass


# ==============================================
# HIGHLIGHTER
# ==============================================

class LuaHighlighter:
    KEYWORDS = {
        'and', 'break', 'do', 'else', 'elseif', 'end', 'false', 'for',
        'function', 'if', 'in', 'local', 'nil', 'not', 'or', 'repeat',
        'return', 'then', 'true', 'until', 'while', 'self'
    }
    PATTERNS = [
        (r'--\[\[.*?\]\]', 'comment'),
        (r'--[^\n]*', 'comment'),
        (r'\[\[.*?\]\]', 'string'),
        (r'"(?:\\.|[^"\\])*"', 'string'),
        (r"'(?:\\.|[^'\\])*'", 'string'),
        (r'\b\d+\.?\d*\b', 'number'),
        (r'\b[A-Za-z_]\w*\b', 'word'),
    ]

    @classmethod
    def apply(cls, text_widget, theme):
        try:
            for tag in ('comment', 'string', 'number', 'keyword'):
                text_widget.tag_remove(tag, '1.0', tk.END)
            content = text_widget.get('1.0', tk.END)
            if not content.strip():
                return
            for pattern, kind in cls.PATTERNS:
                for match in re.finditer(pattern, content, re.DOTALL):
                    start = "1.0+" + str(match.start()) + "c"
                    end = "1.0+" + str(match.end()) + "c"
                    if kind == 'word':
                        if match.group() in cls.KEYWORDS:
                            text_widget.tag_add('keyword', start, end)
                    elif kind in ('comment', 'string', 'number'):
                        text_widget.tag_add(kind, start, end)
            text_widget.tag_config('comment', foreground=theme['comment'])
            text_widget.tag_config('string', foreground=theme['string'])
            text_widget.tag_config('number', foreground=theme['number'])
            text_widget.tag_config('keyword', foreground=theme['keyword'])
        except Exception as e:
            print("Erro highlight: " + str(e))


# ==============================================
# FORMATTER
# ==============================================

class LuaFormatter:
    OPENERS = re.compile(r'\b(function|if|for|while|repeat|do)\b')

    @classmethod
    def format(cls, code, indent="    "):
        result = []
        level = 0
        for line in code.split('\n'):
            s = line.strip()
            if re.match(r'^\s*(end|until|else|elseif)\b', line):
                level = max(0, level - 1)
            result.append((indent * level + s) if s else '')
            if re.match(r'^\s*(else|elseif)\b', line):
                level += 1
            opens = len(cls.OPENERS.findall(s))
            closes = len(re.findall(r'\bend\b', s))
            if s.startswith('elseif') or s.startswith('else'):
                continue
            if re.match(r'^\s*(for|while)\b', s) and ' do' in s:
                opens = max(1, opens - 1)
            level = max(0, level + opens - closes)
        return '\n'.join(result)


# ==============================================
# AI
# ==============================================

class AIAssistant:
    def __init__(self, api_key=None, model="openai/gpt-oss-120b", history=None):
        self.api_key = api_key
        self.client = None
        self.model = model
        self.history = history
        self.context = []
        self.max_context = 10
        self.beginner_mode = False
        if GROQ_AVAILABLE and api_key:
            self.client = Groq(api_key=api_key)

    def set_api_key(self, k):
        self.api_key = k
        if GROQ_AVAILABLE and k:
            self.client = Groq(api_key=k)

    def set_model(self, m): self.model = m
    def set_beginner(self, v): self.beginner_mode = bool(v)
    def is_ready(self): return self.client is not None

    def get_system_prompt(self):
        base = ("Voce e um assistente especialista em Garry's Mod e Lua.\n"
                "Regras:\n"
                "1. NUNCA reescreva o script inteiro (a menos que peca)\n"
                "2. Foque em corrigir BUGS especificos\n"
                "3. Seja curto e direto\n"
                "4. Explique em portugues\n"
                "5. Quando retornar codigo, use SEMPRE um unico bloco lua\n")
        if self.beginner_mode:
            base += ("\nMODO INICIANTE ATIVO:\n"
                     "- Explique como se o usuario nunca tivesse usado Lua/GMod\n"
                     "- Defina termos tecnicos\n"
                     "- Use analogias quando ajudar\n"
                     "- Diga EXATAMENTE onde colocar o codigo (arquivo/pasta)\n")
        base += "RESPONDA EM PORTUGUES."
        return base

    def ask(self, question, code_context="", conv_id=None, truncator=None):
        if not self.is_ready():
            return {"error": "API key nao configurada"}

        was_truncated = False
        lines_removed = 0

        # Trunca codigo se necessario
        if code_context and truncator:
            code_context, was_truncated, lines_removed = truncator.truncate(
                code_context, AI_MAX_CODE_CHARS)

        messages = [{"role": "system", "content": self.get_system_prompt()}]
        if conv_id and self.history:
            for c in self.history.get_conversations():
                if c['id'] == conv_id:
                    for msg in c['messages'][-self.max_context:]:
                        messages.append({
                            "role": msg['role'],
                            "content": msg['content'],
                        })
                    break
        else:
            for msg in self.context[-self.max_context:]:
                messages.append(msg)

        if code_context:
            question = question + "\n\nCODIGO:\n```lua\n" + code_context + "\n```"
        messages.append({"role": "user", "content": question})

        try:
            r = self.client.chat.completions.create(
                model=self.model, messages=messages,
                temperature=0.7, max_tokens=2000)
            answer = r.choices[0].message.content

            if conv_id and self.history:
                self.history.add_message(conv_id, "user", question)
                self.history.add_message(conv_id, "assistant", answer)
            else:
                self.context.append({"role": "user", "content": question})
                self.context.append({"role": "assistant", "content": answer})

            return {
                "answer": answer,
                "truncated": was_truncated,
                "lines_removed": lines_removed,
            }
        except Exception as e:
            return {"error": str(e)}

    def clear_context(self):
        self.context = []


# ==============================================
# TEMPLATES
# ==============================================

TEMPLATES = {
    'swep_308': '''--[[
    {name}
    SWEP 308 Base
]]

SWEP.Base = "weapon_308_base"
SWEP.Author = "SeuNome"
SWEP.PrintName = "{name}"
SWEP.Category = "Minhas Armas"
SWEP.Instructions = "LMB - Atirar | RMB - Mira | R - Recarregar"
SWEP.ViewModel = "models/weapons/cstrike/c_pist_deagle.mdl"
SWEP.WorldModel = "models/weapons/w_pist_deagle.mdl"
SWEP.ViewModelFOV = 70
SWEP.UseHands = true
SWEP.HoldType = "pistol"
SWEP.Slot = 2
SWEP.SlotPos = 1
SWEP.Weight = 5
SWEP.Spawnable = true
SWEP.AdminSpawnable = true
SWEP.DrawCrosshair = true
SWEP.DrawAmmo = false
SWEP.FiresUnderwater = false
SWEP.Primary.ClipSize = 30
SWEP.Primary.DefaultClip = 60
SWEP.Primary.Automatic = true
SWEP.Primary.Ammo = "Battery"
SWEP.PA_Damage = 20
SWEP.PA_Num = 1
SWEP.PA_Delay = 0.1
SWEP.PA_TakeAmmo = 1
SWEP.PA_Spread = 0.02
SWEP.PA_Sound = "weapons/pistol/pistol_fire.wav"

function SWEP:Initialize()
    self:SetWeaponHoldType(self.HoldType)
    self.BaseClass.Initialize(self)
end

function SWEP:PrimaryAttack()
    if not self:CanPrimaryAttack() then return end
    self:TakePrimaryAmmo(self.PA_TakeAmmo)
    self:EmitSound(self.PA_Sound)
    self:SendWeaponAnim(ACT_VM_PRIMARYATTACK)
    self:GetOwner():ViewPunch(Angle(math.Rand(-0.5, -0.2), math.Rand(-0.3, 0.3), 0))
    local ply = self:GetOwner()
    local bullet = {{
        Attacker = ply, Damage = self.PA_Damage, Num = self.PA_Num,
        Tracer = 1, Force = 5,
        Spread = Vector(self.PA_Spread, self.PA_Spread, 0),
        Dir = ply:GetAimVector(), Src = ply:GetShootPos()
    }}
    ply:FireBullets(bullet)
    self:SetNextPrimaryFire(CurTime() + self.PA_Delay)
end

function SWEP:Reload()
    if self:Clip1() < self.Primary.ClipSize then
        self:DefaultReload(ACT_VM_RELOAD)
        return true
    end
    return false
end

print("[{name}] Carregado!")
''',

    'swep_standalone': '''--[[
    {name}
    SWEP Standalone
]]

if SERVER then AddCSLuaFile() end

SWEP.Base = "weapon_base"
SWEP.Author = "SeuNome"
SWEP.PrintName = "{name}"
SWEP.Category = "Minhas Armas"
SWEP.Instructions = "LMB - Atirar | R - Recarregar"
SWEP.ViewModel = "models/weapons/cstrike/c_pist_deagle.mdl"
SWEP.WorldModel = "models/weapons/w_pist_deagle.mdl"
SWEP.ViewModelFOV = 70
SWEP.UseHands = true
SWEP.HoldType = "pistol"
SWEP.Slot = 2
SWEP.SlotPos = 1
SWEP.Weight = 5
SWEP.Spawnable = true
SWEP.AdminSpawnable = true
SWEP.Primary.ClipSize = 30
SWEP.Primary.DefaultClip = 60
SWEP.Primary.Automatic = true
SWEP.Primary.Ammo = "pistol"
SWEP.Primary.Delay = 0.1

function SWEP:Initialize()
    self:SetWeaponHoldType(self.HoldType)
end

function SWEP:Deploy()
    self:SetWeaponHoldType(self.HoldType)
    return true
end

function SWEP:CanPrimaryAttack()
    if self:Clip1() <= 0 then
        self:EmitSound("Weapon_Pistol.Empty")
        self:SetNextPrimaryFire(CurTime() + 0.2)
        return false
    end
    return true
end

function SWEP:PrimaryAttack()
    if not self:CanPrimaryAttack() then return end
    self:TakePrimaryAmmo(1)
    self:EmitSound("weapons/pistol/pistol_fire.wav")
    self:SendWeaponAnim(ACT_VM_PRIMARYATTACK)
    local ply = self:GetOwner()
    ply:FireBullets({{
        Attacker = ply, Damage = 20, Num = 1, Tracer = 1, Force = 5,
        Spread = Vector(0.02, 0.02, 0),
        Dir = ply:GetAimVector(), Src = ply:GetShootPos()
    }})
    self:SetNextPrimaryFire(CurTime() + self.Primary.Delay)
end

function SWEP:Reload()
    if self:Clip1() < self.Primary.ClipSize then
        self:DefaultReload(ACT_VM_RELOAD)
        return true
    end
    return false
end

print("[{name}] Carregado!")
''',

    'entity_vj': '''--[[ {name} - VJ Base ]]

if SERVER then AddCSLuaFile() end

ENT.Type = "anim"
ENT.Base = "base_vj_entity"
ENT.PrintName = "{name}"
ENT.Category = "Minhas Entidades (VJ)"
ENT.Spawnable = true
ENT.AdminSpawnable = true
ENT.VJ_NPC_Class = {{"CLASS_NONE"}}
ENT.VJ_IsMonster = true
ENT.VJ_IsHuman = false

function ENT:CustomOnInitialize()
    self:SetModel("models/hunter/blocks/sphere1x1.mdl")
    self:PhysicsInit(SOLID_VPHYSICS)
    self:SetMoveType(MOVETYPE_VPHYSICS)
    self:SetSolid(SOLID_VPHYSICS)
    self:SetHealth(100)
    self:SetMaxHealth(100)
end

if CLIENT then
    function ENT:Draw() self:DrawModel() end
end

print("[{name}] Carregado!")
''',

    'entity_drg': '''--[[ {name} - DRG Base ]]

if SERVER then AddCSLuaFile() end

ENT.Type = "anim"
ENT.Base = "base_drg_entity"
ENT.PrintName = "{name}"
ENT.Category = "Minhas Entidades (DRG)"
ENT.Spawnable = true
ENT.AdminSpawnable = true

function ENT:Initialize()
    if SERVER then
        self:SetModel("models/hunter/blocks/sphere1x1.mdl")
        self:PhysicsInit(SOLID_VPHYSICS)
        self:SetMoveType(MOVETYPE_VPHYSICS)
        self:SetSolid(SOLID_VPHYSICS)
        self:SetHealth(100)
    end
end

function ENT:Think()
    self:NextThink(CurTime() + 0.1)
    return true
end

function ENT:Use(a, c)
    if IsValid(a) and a:IsPlayer() then
        a:ChatPrint("Voce interagiu com {name}!")
    end
end

if CLIENT then
    function ENT:Draw() self:DrawModel() end
end

print("[{name}] Carregado!")
''',

    'entity_standalone': '''--[[ {name} - Entidade Standalone ]]

if SERVER then
    AddCSLuaFile("shared.lua")
    AddCSLuaFile("cl_init.lua")
    include("shared.lua")
else
    include("shared.lua")
end

ENT.Type = "anim"
ENT.Base = "base_anim"
ENT.PrintName = "{name}"
ENT.Category = "Minhas Entidades"
ENT.Spawnable = true
ENT.AdminSpawnable = true

function ENT:Initialize()
    if SERVER then
        self:SetModel("models/hunter/blocks/sphere1x1.mdl")
        self:PhysicsInit(SOLID_VPHYSICS)
        self:SetMoveType(MOVETYPE_VPHYSICS)
        self:SetSolid(SOLID_VPHYSICS)
        local phys = self:GetPhysicsObject()
        if IsValid(phys) then phys:Wake() end
    end
end

function ENT:Think()
    self:NextThink(CurTime() + 0.1)
    return true
end

function ENT:Use(a, c)
    if IsValid(a) and a:IsPlayer() then
        a:ChatPrint("Voce interagiu com {name}!")
    end
end

print("[{name}] Carregado!")
''',
}

ENTITY_INIT_TEMPLATE = '''-- {name} init.lua (server)
AddCSLuaFile("shared.lua")
AddCSLuaFile("cl_init.lua")
include("shared.lua")
'''

ENTITY_CL_INIT_TEMPLATE = '''-- {name} cl_init.lua (client)
include("shared.lua")

function ENT:Draw()
    self:DrawModel()
end
'''


# ==============================================
# EDITOR PRINCIPAL
# ==============================================

class GMODEditor:
    def __init__(self, root):
        self.root = root
        self.root.title("GMod 13 Addon Editor v" + VERSION)

        self._logo_icon = None
        try:
            if os.path.exists(LOGO_ICO):
                self.root.iconbitmap(LOGO_ICO)
            elif os.path.exists(LOGO_PNG) and PIL_AVAILABLE:
                self._logo_icon = ImageTk.PhotoImage(Image.open(LOGO_PNG))
                self.root.iconphoto(True, self._logo_icon)
        except Exception:
            pass

        self.config = Config()
        self.theme_name = self.config.get('theme', 'dark')
        if self.theme_name not in THEMES:
            self.theme_name = 'dark'
        self.theme = THEMES[self.theme_name]

        self.icons_enabled = self.config.get('use_icons', True)
        self.icons = IconManager()
        self._check_icons()

        self.plugin_manager = PluginManager()
        self.plugin_manager.reload()

        self.snippet_manager = SnippetManager()
        self.snippet_manager.reload()

        self.linter = LuaLinter()
        self.git = GitManager()
        self.truncator = CodeTruncator()

        self.ai_history = AIHistoryManager()
        self.current_conv_id = None
        last_conv = self.ai_history.get_last()
        if last_conv:
            self.current_conv_id = last_conv['id']

        self._apply_ttk_style()

        w = self.config.get('window_width', 1400)
        h = self.config.get('window_height', 800)
        self.root.geometry(str(w) + "x" + str(h))
        self.root.minsize(1200, 650)

        self.current_project = None
        self.project_path = None
        self.gmod_path = self.config.get('gmod_path', self.find_gmod())
        self.output_path = self.config.get('output_path', '')
        self.open_tabs = {}
        self.current_tab = None
        self.current_tab_path = None
        self.path_to_item = {}
        self.file_mtimes = {}

        api_key = self.config.get('groq_api_key', '')
        model = self.config.get('groq_model', 'openai/gpt-oss-120b')
        self.ai = AIAssistant(api_key, model, self.ai_history)
        self.api_key = api_key
        self.ai_model = model
        self.ai_auto_truncate = self.config.get('ai_auto_truncate', True)

        self.auto_save_enabled = self.config.get('auto_save_enabled', True)
        self.auto_save_interval = self.config.get('auto_save_interval', 60)
        self._auto_save_job = None
        self._hl_job = None
        self._lint_jobs = {}
        self.linter_enabled = self.config.get('linter_enabled', True)

        self.autocomplete_enabled = self.config.get('autocomplete_enabled', True)
        self.autocomplete = AutoCompletePopup(self)
        self._ac_installed = {}

        self.create_menu()
        self.create_main_layout()
        self.create_status_bar()

        self.update_status("Pronto! v" + VERSION + " | Tema: " + self.theme['name'])
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        if DND_AVAILABLE:
            self.enable_drag_drop()

        self.schedule_auto_save()

        last = self.config.get('last_project', '')
        if last and os.path.exists(last) and self._is_valid_project(last):
            self.load_project(last)
        elif last:
            self.config['last_project'] = ''
            self.config.save()

    def _is_valid_project(self, path):
        if not path or not os.path.isdir(path):
            return False
        if os.path.exists(os.path.join(path, "project.json")):
            return True
        lua_dir = os.path.join(path, "lua")
        if os.path.isdir(lua_dir):
            try:
                return len(os.listdir(lua_dir)) > 0
            except Exception:
                return False
        return False

    def _apply_ttk_style(self):
        try:
            style = ttk.Style()
            theme_use = 'clam' if self.theme_name == 'dark' else 'default'
            try:
                style.theme_use(theme_use)
            except Exception:
                pass
            if self.theme_name == 'dark':
                style.configure('.', background='#2d2d2d', foreground='#d4d4d4')
                style.configure('TFrame', background='#2d2d2d')
                style.configure('TLabel', background='#2d2d2d', foreground='#d4d4d4')
                style.configure('TButton', background='#3c3c3c', foreground='#d4d4d4', borderwidth=0)
                style.map('TButton', background=[('active', '#4a4a4a')],
                          foreground=[('active', '#ffffff')])
                style.configure('TEntry', fieldbackground='#3c3c3c',
                                foreground='#d4d4d4', borderwidth=0)
                style.configure('TCombobox', fieldbackground='#3c3c3c',
                                foreground='#d4d4d4')
                style.configure('Treeview', background='#252526',
                                foreground='#d4d4d4', fieldbackground='#252526',
                                borderwidth=0)
                style.map('Treeview', background=[('selected', '#094771')],
                          foreground=[('selected', '#ffffff')])
                style.configure('Treeview.Heading', background='#3c3c3c',
                                foreground='#d4d4d4')
                style.configure('TScrollbar', background='#3c3c3c',
                                borderwidth=0, arrowcolor='#d4d4d4')
                style.configure('TPanedwindow', background='#1e1e1e')
            else:
                style.configure('.', background='#f3f3f3', foreground='#1e1e1e')
        except Exception as e:
            print("ttk: " + str(e))

    def _check_icons(self):
        if not PIL_AVAILABLE or not os.path.exists(ICONS_DIR):
            self.icons_enabled = False
            return
        pngs = [f for f in os.listdir(ICONS_DIR) if f.endswith('.png')]
        if not pngs:
            self.icons_enabled = False

    def menu_label(self, name, text):
        emoji = IconManager.FALLBACKS.get(name, "")
        return (emoji + " " + text).strip()

    def toggle_theme(self):
        self.theme_name = 'light' if self.theme_name == 'dark' else 'dark'
        self.theme = THEMES[self.theme_name]
        self.config['theme'] = self.theme_name
        self.config.save()
        self.icons.clear()
        self._apply_ttk_style()
        self._apply_theme_to_widgets()
        if self.project_path:
            self.refresh_explorer()
        self.update_status("Tema: " + self.theme['name'])

    def toggle_autocomplete(self):
        self.autocomplete_enabled = not self.autocomplete_enabled
        self.config['autocomplete_enabled'] = self.autocomplete_enabled
        self.config.save()
        if not self.autocomplete_enabled:
            self.autocomplete.hide()
        self.update_status("Auto-complete " + ("ON" if self.autocomplete_enabled else "OFF"))

    def toggle_linter(self):
        self.linter_enabled = not self.linter_enabled
        self.config['linter_enabled'] = self.linter_enabled
        self.config.save()
        if not self.linter_enabled:
            for fp in list(self._lint_jobs.keys()):
                try:
                    self.root.after_cancel(self._lint_jobs[fp])
                except Exception:
                    pass
            self._lint_jobs.clear()
            self._clear_all_error_marks()
        self.update_status("Linter " + ("ON" if self.linter_enabled else "OFF"))

    def _apply_theme_to_widgets(self):
        t = self.theme
        for fp, (frame, tw, ln) in self.open_tabs.items():
            try:
                tw.config(bg=t['bg'], fg=t['fg'],
                          insertbackground=t['insert'],
                          selectbackground=t['select_bg'])
                ln.config(bg=t['line_bg'], fg=t['line_fg'])
                LuaHighlighter.apply(tw, t)
            except Exception:
                pass
        for fp, btn in self.tab_buttons.items():
            active = (fp == self.current_tab_path)
            try:
                btn.config(bg=t['tab_bg_active'] if active else t['tab_bg'],
                           fg=t['tab_fg_active'] if active else t['tab_fg'])
            except Exception:
                pass

    def find_gmod(self):
        for p in [
            "C:/Program Files (x86)/Steam/steamapps/common/GarrysMod",
            "C:/Program Files/Steam/steamapps/common/GarrysMod",
            "D:/Program Files (x86)/Steam/steamapps/common/GarrysMod",
            "E:/Steam/steamapps/common/GarrysMod",
            "D:/SteamLibrary/steamapps/common/GarrysMod",
            "E:/SteamLibrary/steamapps/common/GarrysMod",
        ]:
            if os.path.exists(p):
                return p
        return ""

    def save_config(self):
        self.config['gmod_path'] = self.gmod_path
        self.config['output_path'] = self.output_path
        if getattr(self, 'api_key', ''):
            self.config['groq_api_key'] = self.api_key
        self.config['groq_model'] = getattr(self, 'ai_model', 'openai/gpt-oss-120b')
        if self.current_project and self.project_path:
            self.config['last_project'] = self.project_path
        try:
            self.config['window_width'] = self.root.winfo_width()
            self.config['window_height'] = self.root.winfo_height()
        except Exception:
            pass
        self.config['auto_save_enabled'] = self.auto_save_enabled
        self.config['auto_save_interval'] = self.auto_save_interval
        self.config['use_icons'] = self.icons_enabled
        self.config['theme'] = self.theme_name
        self.config['autocomplete_enabled'] = self.autocomplete_enabled
        self.config['linter_enabled'] = self.linter_enabled
        self.config['ai_auto_truncate'] = self.ai_auto_truncate
        self.config.save()

    def schedule_auto_save(self):
        if self._auto_save_job:
            try:
                self.root.after_cancel(self._auto_save_job)
            except Exception:
                pass
        self._auto_save_job = self.root.after(
            max(10, self.auto_save_interval) * 1000, self._auto_save_tick)

    def _auto_save_tick(self):
        try:
            if self.auto_save_enabled and self.open_tabs:
                self.save_all_tabs()
        except Exception:
            pass
        self.schedule_auto_save()

    def refresh_project(self):
        if not self.project_path or not self.current_project:
            messagebox.showinfo("Refresh", "Nenhum projeto aberto.")
            return
        if not os.path.exists(self.project_path):
            messagebox.showerror("Erro", "Pasta do projeto nao existe.")
            self._clear_project()
            return
        if self.open_tabs:
            self.save_all_tabs()
        self.load_explorer(self.project_path)
        self.load_properties()
        for fp in list(self.open_tabs.keys()):
            if os.path.exists(fp):
                try:
                    self.file_mtimes[fp] = os.path.getmtime(fp)
                except Exception:
                    pass
        self.update_status("Projeto recarregado")

    def _clear_project(self):
        for fp in list(self.open_tabs.keys()):
            try:
                self.close_tab(fp)
            except Exception:
                pass
        self.current_project = None
        self.project_path = None
        self.path_to_item = {}
        try:
            self.explorer_tree.delete(*self.explorer_tree.get_children())
        except Exception:
            pass
        for w in self.props_frame.winfo_children():
            w.destroy()
        ttk.Label(self.props_frame, text="Selecione um projeto",
                  font=("Arial", 10), foreground=self.theme['fg_dim']).pack(pady=20)
        self.config['last_project'] = ''
        self.config.save()

    def enable_drag_drop(self):
        if not DND_AVAILABLE or not hasattr(self.root, 'drop_target_register'):
            return
        try:
            self.root.drop_target_register('DND_Files')
            self.root.dnd_bind('<<Drop>>', self.on_drop)
        except Exception:
            pass

    def on_drop(self, event):
        if not self.project_path:
            messagebox.showinfo("Aviso", "Abra um projeto!")
            return
        data = event.data
        if isinstance(data, str):
            if data.startswith('{'):
                files = re.findall(r'\{([^}]+)\}', data) or [data]
            elif ' ' in data:
                files = data.split()
            else:
                files = [data]
        else:
            files = list(data)
        n = 0
        for f in files:
            f = f.strip('{}')
            if os.path.isfile(f) and self.import_file(f):
                n += 1
            elif os.path.isdir(f) and self.import_folder(f):
                n += 1
        if n:
            self.update_status(str(n) + " importados")
            self.refresh_explorer()

    def import_file(self, file_path, target_item=None):
        if not self.project_path:
            return False
        try:
            if target_item:
                dest = self.get_item_path(target_item)
                if dest and os.path.isfile(dest):
                    dest = os.path.dirname(dest)
                if not dest or not os.path.isdir(dest):
                    dest = self.project_path
            else:
                dest = self.get_destination_folder(file_path)
            os.makedirs(dest, exist_ok=True)
            name = os.path.basename(file_path)
            dp = os.path.join(dest, name)
            if os.path.exists(dp) and not messagebox.askyesno(
                    "Existe", "'" + name + "' ja existe. Sobrescrever?"):
                return False
            shutil.copy2(file_path, dp)
            return True
        except Exception as e:
            messagebox.showerror("Erro", str(e))
            return False

    def import_folder(self, folder_path, target_item=None):
        if not self.project_path:
            return False
        try:
            if target_item:
                dest = self.get_item_path(target_item)
                if dest and os.path.isfile(dest):
                    dest = os.path.dirname(dest)
                if not dest or not os.path.isdir(dest):
                    dest = self.project_path
            else:
                dest = self.get_destination_folder(folder_path)
            name = os.path.basename(folder_path)
            dp = os.path.join(dest, name)
            if os.path.exists(dp) and not messagebox.askyesno(
                    "Existe", "'" + name + "' ja existe. Mesclar?"):
                return False
            shutil.copytree(folder_path, dp, dirs_exist_ok=True)
            return True
        except Exception as e:
            messagebox.showerror("Erro", str(e))
            return False

    def get_destination_folder(self, file_path):
        name = os.path.basename(file_path)
        ext = os.path.splitext(name)[1].lower()
        low = name.lower()
        fmap = {
            '.lua': 'lua', '.txt': 'lua',
            '.png': 'materials', '.jpg': 'materials', '.jpeg': 'materials',
            '.tga': 'materials', '.vmt': 'materials', '.vtf': 'materials',
            '.mdl': 'models', '.vvd': 'models', '.vtx': 'models',
            '.phy': 'models', '.smd': 'models', '.qc': 'models',
            '.wav': 'sound', '.mp3': 'sound', '.ogg': 'sound', '.flac': 'sound',
            '.pcf': 'particles', '.zip': 'resource', '.json': 'resource',
        }
        if low.startswith('weapon'):
            return os.path.join(self.project_path, 'lua', 'weapons')
        if low.startswith(('ent_', 'npc_')):
            return os.path.join(self.project_path, 'lua', 'entities')
        if 'sound' in file_path.lower() or 'audio' in file_path.lower():
            return os.path.join(self.project_path, 'sound')
        if 'texture' in file_path.lower() or 'material' in file_path.lower():
            return os.path.join(self.project_path, 'materials')
        f = fmap.get(ext)
        if f:
            return os.path.join(self.project_path, f)
        return self.project_path

    def open_import_dialog(self, target_item=None):
        if not self.project_path:
            messagebox.showerror("Erro", "Abra um projeto!")
            return
        files = filedialog.askopenfilenames(
            title="Importar",
            filetypes=[
                ("Suportados",
                 "*.lua *.txt *.png *.jpg *.jpeg *.tga *.vmt *.vtf *.mdl *.vvd *.vtx *.phy *.wav *.mp3 *.ogg *.pcf"),
                ("Lua", "*.lua"), ("Imagens", "*.png *.jpg *.jpeg *.tga"),
                ("Modelos", "*.mdl *.vvd *.vtx *.phy"),
                ("Sons", "*.wav *.mp3 *.ogg"), ("Todos", "*.*"),
            ])
        if not files:
            return
        n = sum(1 for f in files if self.import_file(f, target_item))
        if n:
            self.refresh_explorer()
            self.update_status(str(n) + " importados")

    # =========================================
    # MENU
    # =========================================

    def create_menu(self):
        mb = tk.Menu(self.root)
        self.root.config(menu=mb)
        ml = self.menu_label

        fm = tk.Menu(mb, tearoff=0)
        mb.add_cascade(label="Arquivo", menu=fm)
        fm.add_command(label=ml('new', "Novo Projeto"), command=self.new_project, accelerator="Ctrl+N")
        fm.add_command(label=ml('open', "Abrir Projeto"), command=self.open_project, accelerator="Ctrl+O")
        fm.add_command(label=ml('refresh', "Recarregar Projeto"), command=self.refresh_project, accelerator="F8")
        fm.add_command(label=ml('close', "Fechar Projeto"), command=self._clear_project)
        fm.add_separator()
        fm.add_command(label=ml('save', "Salvar"), command=self.save_current_tab, accelerator="Ctrl+S")
        fm.add_command(label="Salvar Todos", command=self.save_all_tabs)
        fm.add_separator()
        fm.add_command(label=ml('close', "Fechar Tab"), command=self.close_current_tab, accelerator="Ctrl+W")
        fm.add_separator()
        fm.add_command(label=ml('settings', "Configuracoes"), command=self.open_settings)
        fm.add_separator()
        fm.add_command(label="Sair", command=self.on_close, accelerator="Ctrl+Q")

        cm = tk.Menu(mb, tearoff=0)
        mb.add_cascade(label="Criar", menu=cm)
        self._build_create_menu(cm)

        tm = tk.Menu(mb, tearoff=0)
        mb.add_cascade(label="Ferramentas", menu=tm)
        tm.add_command(label=ml('format', "Formatar Codigo Lua"), command=self.format_current_code)
        tm.add_command(label="Corrigir Erros Comuns de Lua", command=self.fix_common_errors)
        tm.add_separator()
        tm.add_command(label=ml('search', "Buscar em Arquivos"), command=self.search_files)
        tm.add_command(label=ml('stats', "Estatisticas"), command=self.show_stats)
        tm.add_separator()
        tm.add_command(label=ml('moon', "Alternar Tema"), command=self.toggle_theme, accelerator="F9")
        ac_state = "Desativar" if self.autocomplete_enabled else "Ativar"
        tm.add_command(label="Auto-complete: " + ac_state,
                       command=self.toggle_autocomplete, accelerator="Ctrl+Space")
        lint_state = "Desativar" if self.linter_enabled else "Ativar"
        tm.add_command(label="Linter: " + lint_state, command=self.toggle_linter)

        am = tk.Menu(mb, tearoff=0)
        mb.add_cascade(label=ml('ai', "IA"), menu=am)
        am.add_command(label="Chat com Historico...", command=self.open_ai_chat)
        am.add_separator()
        am.add_command(label="Corrigir Bug", command=self.ai_fix_bug)
        am.add_command(label="Sugestao", command=self.ai_suggestion)
        am.add_command(label="Explicar Codigo", command=self.ai_explain)
        am.add_command(label="Explicar (modo Iniciante)", command=self.ai_explain_beginner)
        am.add_separator()
        am.add_command(label="Gerar Codigo a partir de Descricao...", command=self.ai_generate_code)
        am.add_command(label="Traduzir Comentarios (PT <-> EN)", command=self.ai_translate_comments)
        am.add_separator()
        trunc_state = "Desativar" if self.ai_auto_truncate else "Ativar"
        am.add_command(label="Auto-truncar codigo grande: " + trunc_state,
                       command=self.toggle_ai_truncate)
        am.add_command(label="Ver tamanho do codigo atual", command=self.show_ai_code_stats)
        am.add_separator()
        am.add_command(label="Historico de Conversas...", command=self.open_ai_history)

        gm = tk.Menu(mb, tearoff=0)
        mb.add_cascade(label=ml('git', "Git"), menu=gm)
        gm.add_command(label="Status", command=self.git_status)
        gm.add_command(label="Commit...", command=self.git_commit_dialog)
        gm.add_command(label="Push", command=self.git_push_dialog)
        gm.add_command(label="Pull", command=self.git_pull_dialog)
        gm.add_separator()
        gm.add_command(label="Inicializar Repositorio", command=self.git_init)
        gm.add_command(label="Ultimos Commits", command=self.git_log)
        gm.add_separator()
        gm.add_command(label="Abrir Pasta do Projeto", command=self.git_open_terminal)

        sm = tk.Menu(mb, tearoff=0)
        mb.add_cascade(label=ml('snippet', "Snippets"), menu=sm)
        sm.add_command(label="Gerenciar Snippets...", command=self.open_snippets_manager)
        sm.add_command(label="Salvar Selecao como Snippet...", command=self.save_selection_as_snippet)
        sm.add_separator()
        sm.add_command(label="Abrir Pasta de Snippets", command=self.open_snippets_folder)

        am2 = tk.Menu(mb, tearoff=0)
        mb.add_cascade(label="Addon", menu=am2)
        am2.add_command(label=ml('compile', "Compilar"), command=self.compile_addon, accelerator="F5")
        am2.add_command(label=ml('validate', "Validar Estrutura"), command=self.validate_structure)
        am2.add_command(label=ml('publish', "Publicar"), command=self.publish_addon, accelerator="F6")
        am2.add_command(label=ml('update', "Atualizar"), command=self.update_addon, accelerator="F7")
        am2.add_separator()
        am2.add_command(label=ml('folder', "Abrir Pasta"), command=self.open_addon_folder)

        pm = tk.Menu(mb, tearoff=0)
        mb.add_cascade(label=ml('plugin', "Plugins"), menu=pm)
        pm.add_command(label="Gerenciar Plugins...", command=self.open_plugins_manager)
        pm.add_command(label=ml('market', "Marketplace..."), command=self.open_marketplace)
        pm.add_separator()
        pm.add_command(label="Recarregar Plugins", command=self.reload_plugins)
        pm.add_command(label="Abrir Pasta de Plugins", command=self.open_plugins_folder)
        pm.add_command(label="Abrir Pasta de Disponiveis", command=self.open_available_folder)
        pm.add_separator()
        pm.add_command(label="Criar Plugin de Exemplo", command=self.create_example_plugin_wizard)

        hm = tk.Menu(mb, tearoff=0)
        mb.add_cascade(label="Ajuda", menu=hm)
        hm.add_command(label=ml('about', "Sobre"), command=self.show_about)

        self.root.bind('<Control-n>', lambda e: self.new_project())
        self.root.bind('<Control-o>', lambda e: self.open_project())
        self.root.bind('<Control-s>', lambda e: self.save_current_tab())
        self.root.bind('<Control-w>', lambda e: self.close_current_tab())
        self.root.bind('<Control-q>', lambda e: self.on_close())
        self.root.bind('<Control-Tab>', lambda e: self.cycle_tab(1))
        self.root.bind('<Control-Shift-Tab>', lambda e: self.cycle_tab(-1))
        self.root.bind('<Control-Shift-C>', lambda e: self._copy_selected_vpk_multi())
        self.root.bind('<Control-space>', lambda e: self.toggle_autocomplete())
        self.root.bind('<F5>', lambda e: self.compile_addon())
        self.root.bind('<F6>', lambda e: self.publish_addon())
        self.root.bind('<F7>', lambda e: self.update_addon())
        self.root.bind('<F8>', lambda e: self.refresh_project())
        self.root.bind('<F9>', lambda e: self.toggle_theme())

    def toggle_ai_truncate(self):
        self.ai_auto_truncate = not self.ai_auto_truncate
        self.config['ai_auto_truncate'] = self.ai_auto_truncate
        self.config.save()
        self.update_status("Auto-truncar IA: " + ("ON" if self.ai_auto_truncate else "OFF"))

    def _build_create_menu(self, cm, target_item=None):
        ml = self.menu_label

        sw = tk.Menu(cm, tearoff=0)
        cm.add_cascade(label=ml('swep', "SWEP"), menu=sw)
        sw.add_command(label="Criar SWEP (308 Base)",
                       command=lambda: self.create_from_template("swep_308", target_item))
        sw.add_command(label="Criar SWEP (Standalone)",
                       command=lambda: self.create_from_template("swep_standalone", target_item))
        try:
            swep_templates = self.plugin_manager.get_templates_by_type("swep")
        except Exception:
            swep_templates = []
        if swep_templates:
            sw.add_separator()
            for t in swep_templates:
                label = t['label'] + "  [" + t['plugin'] + "]"
                sw.add_command(label=label,
                    command=lambda tt=t, ti=target_item: self.create_from_plugin_template(tt, ti))

        en = tk.Menu(cm, tearoff=0)
        cm.add_cascade(label=ml('entity', "ENTITY"), menu=en)
        en.add_command(label="Criar ENTITY (VJ Base)",
                       command=lambda: self.create_from_template("entity_vj", target_item))
        en.add_command(label="Criar ENTITY (DRG Base)",
                       command=lambda: self.create_from_template("entity_drg", target_item))
        en.add_command(label="Criar ENTITY (Standalone)",
                       command=lambda: self.create_from_template("entity_standalone", target_item))
        try:
            ent_templates = self.plugin_manager.get_templates_by_type("entity")
        except Exception:
            ent_templates = []
        if ent_templates:
            en.add_separator()
            for t in ent_templates:
                label = t['label'] + "  [" + t['plugin'] + "]"
                en.add_command(label=label,
                    command=lambda tt=t, ti=target_item: self.create_from_plugin_template(tt, ti))

        try:
            snips = self.snippet_manager.get_all()
        except Exception:
            snips = []
        if snips:
            sn_menu = tk.Menu(cm, tearoff=0)
            cm.add_cascade(label=ml('snippet', "Snippets"), menu=sn_menu)
            for s in snips:
                sn_menu.add_command(label=s['name'],
                    command=lambda ss=s: self.insert_snippet(ss))

        try:
            lua_templates = self.plugin_manager.get_templates_by_type("lua")
        except Exception:
            lua_templates = []
        if lua_templates:
            lm = tk.Menu(cm, tearoff=0)
            cm.add_cascade(label="Lua (plugins)", menu=lm)
            for t in lua_templates:
                label = t['label'] + "  [" + t['plugin'] + "]"
                lm.add_command(label=label,
                    command=lambda tt=t, ti=target_item: self.create_from_plugin_template(tt, ti))

        cm.add_separator()
        cm.add_command(label=ml('file_lua', "Arquivo Lua"),
                       command=lambda: self.create_file("lua", target_item))
        cm.add_command(label=ml('file_txt', "Script Paste"),
                       command=lambda: self.create_file("paste", target_item))
        cm.add_command(label=ml('file_img', "PNG"),
                       command=lambda: self.create_file("png", target_item))
        cm.add_command(label=ml('file_img', "JPG"),
                       command=lambda: self.create_file("jpg", target_item))
        cm.add_separator()
        cm.add_command(label=ml('folder', "Nova Pasta"),
                       command=lambda: self.create_folder(target_item))
        cm.add_separator()
        cm.add_command(label=ml('publish', "Exportar Asset"),
                       command=lambda: self.export_asset(target_item))
        cm.add_command(label="Importar Arquivos",
                       command=lambda: self.open_import_dialog(target_item))

    # =========================================
    # LINTER / FIXER
    # =========================================

    def _schedule_lint(self, file_path):
        if not self.linter_enabled or not self.linter.available:
            return
        if file_path in self._lint_jobs:
            try:
                self.root.after_cancel(self._lint_jobs[file_path])
            except Exception:
                pass
        self._lint_jobs[file_path] = self.root.after(
            LINT_DELAY_MS, lambda: self._run_lint(file_path))

    def _run_lint(self, file_path):
        self._lint_jobs.pop(file_path, None)
        if file_path not in self.open_tabs or not self.linter_enabled:
            return
        try:
            _, tw, _ = self.open_tabs[file_path]
            code = tw.get('1.0', tk.END)
        except Exception:
            return
        ok, line, msg = self.linter.check(code)
        try:
            tw.tag_remove('error_line', '1.0', tk.END)
        except Exception:
            pass
        if ok:
            if self.current_tab_path == file_path:
                self.lint_status.config(text="")
            return
        if line:
            try:
                start = str(line) + ".0"
                end = str(line) + ".end"
                tw.tag_add('error_line', start, end)
                tw.tag_config('error_line', background=self.theme['error_bg'])
            except Exception:
                pass
        if self.current_tab_path == file_path:
            short = msg[:60] + "..." if len(msg) > 60 else msg
            if line:
                self.lint_status.config(text="Lua err L" + str(line))
            else:
                self.lint_status.config(text="Lua: erro")
            self.update_status("Erro Lua: " + short)

    def _clear_all_error_marks(self):
        for fp, data in self.open_tabs.items():
            try:
                _, tw, _ = data
                tw.tag_remove('error_line', '1.0', tk.END)
            except Exception:
                pass
        try:
            self.lint_status.config(text="")
        except Exception:
            pass

    def fix_common_errors(self):
        if not self.current_tab:
            messagebox.showinfo("Corrigir", "Nenhum arquivo aberto.")
            return
        try:
            code = self.current_tab.get('1.0', tk.END)
        except Exception:
            return
        issues = LuaCommonFixes.find_issues(code)
        if not issues:
            messagebox.showinfo("Corrigir Erros", "Nenhum erro comum encontrado.")
            return
        t = self.theme
        w = tk.Toplevel(self.root)
        w.title("Erros Comuns Encontrados")
        w.geometry("700x500")
        w.transient(self.root)
        w.config(bg=t['bg'])
        f = ttk.Frame(w, padding="10")
        f.pack(fill=tk.BOTH, expand=True)
        ttk.Label(f, text=str(len(issues)) + " problema(s)",
                  font=("Arial", 11, "bold")).pack(anchor=tk.W)
        ttk.Separator(f, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=5)
        tf = ttk.Frame(f)
        tf.pack(fill=tk.BOTH, expand=True)
        txt = tk.Text(tf, wrap=tk.WORD, font=("Consolas", 9),
                      bg=t['bg'], fg=t['fg'])
        txt.pack(fill=tk.BOTH, expand=True)
        for iss in issues:
            txt.insert(tk.END, "Linha " + str(iss['line']) + ": " + iss['desc'] + "\n")
            txt.insert(tk.END, "  Antes: " + iss['old'].strip() + "\n")
            txt.insert(tk.END, "  Depois: " + iss['new'].strip() + "\n\n")
        txt.config(state='disabled')
        bf = ttk.Frame(f)
        bf.pack(fill=tk.X, pady=10)

        def apply_fix():
            new_code, count = LuaCommonFixes.auto_fix(code)
            try:
                self.current_tab.delete('1.0', tk.END)
                self.current_tab.insert('1.0', new_code)
                LuaHighlighter.apply(self.current_tab, self.theme)
                self._schedule_lint(self.current_tab_path)
                self.update_status("Corrigidos " + str(count))
                w.destroy()
            except Exception as e:
                messagebox.showerror("Erro", str(e))

        ttk.Button(bf, text="Aplicar Correcao",
                   command=apply_fix).pack(side=tk.LEFT, padx=5)
        ttk.Button(bf, text="Fechar", command=w.destroy).pack(side=tk.RIGHT, padx=5)

    # =========================================
    # IA - CHAT E FUNCOES
    # =========================================

    def open_ai_chat(self):
        t = self.theme
        w = tk.Toplevel(self.root)
        w.title("IA - Chat")
        w.geometry("780x620")
        w.transient(self.root)
        w.config(bg=t['bg'])
        f = ttk.Frame(w, padding="10")
        f.pack(fill=tk.BOTH, expand=True)

        hdr = ttk.Frame(f)
        hdr.pack(fill=tk.X)
        ttk.Label(hdr, text="Chat com IA", font=("Arial", 12, "bold")).pack(side=tk.LEFT)

        convs = self.ai_history.get_conversations()
        conv_names = ["[Nova conversa]"] + [
            (c['title'][:40] + " - " + c['created'][:10]) for c in convs
        ]
        conv_var = tk.StringVar(value=conv_names[0] if conv_names else "")
        conv_combo = ttk.Combobox(hdr, textvariable=conv_var, values=conv_names,
                                   width=45, state='readonly')
        conv_combo.pack(side=tk.RIGHT, padx=5)

        # Info tokens
        info_frame = ttk.Frame(f)
        info_frame.pack(fill=tk.X, pady=(5, 0))
        token_label = ttk.Label(info_frame, text="", font=("Arial", 8))
        token_label.pack(side=tk.LEFT)
        trunc_label = ttk.Label(info_frame, text="", font=("Arial", 8, "italic"),
                                 foreground="#f48771")
        trunc_label.pack(side=tk.RIGHT)

        ttk.Separator(f, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=5)

        chat_frame = ttk.Frame(f)
        chat_frame.pack(fill=tk.BOTH, expand=True)
        chat_box = tk.Text(chat_frame, wrap=tk.WORD, font=("Consolas", 10),
                           bg=t['bg'], fg=t['fg'], insertbackground=t['insert'])
        chat_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb = ttk.Scrollbar(chat_frame, orient=tk.VERTICAL, command=chat_box.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        chat_box.config(yscrollcommand=sb.set)

        chat_box.tag_config("user", foreground="#569cd6", font=("Consolas", 10, "bold"))
        chat_box.tag_config("ai", foreground="#4ec9b0", font=("Consolas", 10, "bold"))
        chat_box.tag_config("info", foreground="#858585", font=("Consolas", 8, "italic"))

        input_frame = ttk.Frame(f)
        input_frame.pack(fill=tk.X, pady=5)
        input_box = tk.Text(input_frame, height=3, wrap=tk.WORD,
                            font=("Consolas", 10), bg=t['bg'], fg=t['fg'],
                            insertbackground=t['insert'])
        input_box.pack(side=tk.LEFT, fill=tk.X, expand=True)

        state = {'conv_id': None, 'busy': False}

        def update_token_info():
            """Atualiza info de tokens."""
            if self.current_tab:
                try:
                    code = self.current_tab.get('1.0', tk.END)
                    chars = len(code)
                    tokens = CodeTruncator.estimate_tokens(code)
                    info_text = ("Codigo atual: " + str(chars) + " chars, ~" +
                                 str(tokens) + " tokens")
                    if chars > AI_MAX_CODE_CHARS:
                        info_text += "  (SERA TRUNCADO para " + str(AI_MAX_CODE_CHARS) + ")"
                        trunc_label.config(text="Codigo grande - sera truncado")
                    else:
                        pct = int(chars * 100 / AI_MAX_CODE_CHARS) if AI_MAX_CODE_CHARS else 0
                        info_text += "  (" + str(pct) + "% do limite)"
                        trunc_label.config(text="")
                    token_label.config(text=info_text)
                except Exception:
                    token_label.config(text="")
            else:
                token_label.config(text="Nenhum arquivo aberto")
                trunc_label.config(text="")

        def load_conversation(idx):
            chat_box.config(state='normal')
            chat_box.delete('1.0', tk.END)
            if idx == 0:
                state['conv_id'] = None
                chat_box.insert(tk.END, "Nova conversa iniciada.\n\n", "info")
                update_token_info()
                return
            real_idx = idx - 1
            if 0 <= real_idx < len(convs):
                c = convs[real_idx]
                state['conv_id'] = c['id']
                for msg in c['messages']:
                    if msg['role'] == 'user':
                        chat_box.insert(tk.END, "Voce: ", "user")
                        chat_box.insert(tk.END, msg['content'] + "\n\n")
                    else:
                        chat_box.insert(tk.END, "IA: ", "ai")
                        chat_box.insert(tk.END, msg['content'] + "\n\n")
            chat_box.see(tk.END)
            update_token_info()

        conv_combo.bind('<<ComboboxSelected>>', lambda e: load_conversation(conv_combo.current()))

        def send():
            if state['busy']:
                return
            msg = input_box.get('1.0', tk.END).strip()
            if not msg:
                return
            if not self.ai.is_ready():
                messagebox.showerror("IA", "API key nao configurada.")
                return

            if state['conv_id'] is None:
                c = self.ai_history.new_conversation(msg[:40])
                state['conv_id'] = c['id']

            chat_box.config(state='normal')
            chat_box.insert(tk.END, "Voce: ", "user")
            chat_box.insert(tk.END, msg + "\n\n")
            chat_box.insert(tk.END, "IA: (pensando...)\n\n", "ai")
            chat_box.see(tk.END)
            input_box.delete('1.0', tk.END)
            state['busy'] = True

            def worker():
                code = ""
                if self.current_tab:
                    try:
                        code = self.current_tab.get('1.0', tk.END).rstrip('\n')
                    except Exception:
                        code = ""
                trunc = self.truncator if self.ai_auto_truncate else None
                r = self.ai.ask(msg, code, state['conv_id'], trunc)

                def update_ui():
                    try:
                        chat_box.config(state='normal')
                        chat_box.delete("end-4l", "end-2l")
                        if "error" in r:
                            chat_box.insert(tk.END, "Erro: " + r['error'] + "\n\n", "ai")
                        else:
                            chat_box.insert(tk.END, r['answer'] + "\n\n", "ai")
                            if r.get('truncated'):
                                info = ("(codigo foi truncado: " +
                                        str(r.get('lines_removed', 0)) +
                                        " linhas removidas)")
                                chat_box.insert(tk.END, info + "\n\n", "info")
                        chat_box.see(tk.END)
                        state['busy'] = False
                    except Exception as e:
                        print("UI: " + str(e))
                self.root.after(0, update_ui)

            threading.Thread(target=worker, daemon=True).start()

        btn_send = ttk.Button(input_frame, text="Enviar", command=send)
        btn_send.pack(side=tk.RIGHT, padx=5, fill=tk.Y)

        input_box.bind('<Control-Return>', lambda e: (send(), "break"))
        ttk.Label(f, text="Ctrl+Enter envia | Codigo grande e truncado automaticamente",
                  font=("Arial", 8, "italic")).pack(anchor=tk.W)

        load_conversation(0)
        try:
            w.focus_force()
            input_box.focus_set()
        except Exception:
            pass

    def show_ai_code_stats(self):
        """Mostra estatisticas do codigo atual relativo aos limites da IA."""
        if not self.current_tab:
            messagebox.showinfo("Info", "Nenhum arquivo aberto.")
            return
        try:
            code = self.current_tab.get('1.0', tk.END)
        except Exception:
            return
        chars = len(code)
        tokens = CodeTruncator.estimate_tokens(code)
        lines = code.count('\n') + 1
        pct = (chars * 100 / AI_MAX_CODE_CHARS) if AI_MAX_CODE_CHARS else 0

        will_truncate = chars > AI_MAX_CODE_CHARS
        truncated, _, removed = self.truncator.truncate(code, AI_MAX_CODE_CHARS)

        msg = "Estatisticas do codigo atual:\n\n"
        msg += "Caracteres: " + str(chars) + "\n"
        msg += "Linhas: " + str(lines) + "\n"
        msg += "~Tokens: " + str(tokens) + "\n\n"
        msg += "Limite para IA: " + str(AI_MAX_CODE_CHARS) + " chars\n"
        msg += "Uso: " + str(int(pct)) + "%\n\n"
        if will_truncate:
            msg += "AVISO: O codigo sera TRUNCADO antes de enviar.\n"
            msg += "Linhas que serao removidas: " + str(removed) + "\n"
            msg += "Tamanho apos truncar: " + str(len(truncated)) + " chars"
        else:
            msg += "OK: Cabe no limite."
        messagebox.showinfo("Tamanho do Codigo", msg)

    def open_ai_history(self):
        t = self.theme
        w = tk.Toplevel(self.root)
        w.title("Historico de Conversas")
        w.geometry("650x480")
        w.transient(self.root)
        w.config(bg=t['bg'])
        f = ttk.Frame(w, padding="10")
        f.pack(fill=tk.BOTH, expand=True)
        ttk.Label(f, text="Historico de conversas com a IA",
                  font=("Arial", 12, "bold")).pack(anchor=tk.W)
        ttk.Label(f, text="Arquivo: " + self.ai_history.history_file,
                  font=("Arial", 8)).pack(anchor=tk.W)
        ttk.Separator(f, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=5)
        cols = ('title', 'created', 'msg')
        tv = ttk.Treeview(f, columns=cols, show='headings', height=15)
        tv.heading('title', text='Titulo')
        tv.heading('created', text='Data')
        tv.heading('msg', text='Msgs')
        tv.column('title', width=300)
        tv.column('created', width=140)
        tv.column('msg', width=60)
        tv.pack(fill=tk.BOTH, expand=True, pady=5)
        sb = ttk.Scrollbar(f, orient=tk.VERTICAL, command=tv.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        tv.config(yscrollcommand=sb.set)

        def refresh():
            tv.delete(*tv.get_children())
            for c in self.ai_history.get_conversations():
                tv.insert("", "end", iid=c['id'],
                          values=(c['title'], c['created'][:19], len(c['messages'])))

        refresh()

        def delete_selected():
            sel = tv.selection()
            if not sel:
                return
            if messagebox.askyesno("Deletar", "Deletar essa conversa?"):
                self.ai_history.delete_conversation(sel[0])
                refresh()

        def clear_all():
            if messagebox.askyesno("Limpar", "Apagar TODAS as conversas?"):
                self.ai_history.clear_all()
                refresh()

        bf = ttk.Frame(f)
        bf.pack(fill=tk.X, pady=10)
        ttk.Button(bf, text="Deletar", command=delete_selected).pack(side=tk.LEFT, padx=3)
        ttk.Button(bf, text="Limpar Tudo", command=clear_all).pack(side=tk.LEFT, padx=3)
        ttk.Button(bf, text="Fechar", command=w.destroy).pack(side=tk.RIGHT, padx=3)

    def ai_fix_bug(self):
        if not self._ensure_ai():
            return
        code = self.get_current_code()
        if code is None:
            return
        bug = simpledialog.askstring("Corrigir Bug", "Descreva o bug:")
        if bug is None:
            return
        q = ("Encontre e corrija o bug.\nBUG: " + bug + "\n\n"
             "Corrija APENAS o bug. Retorne em UM UNICO bloco lua.")
        self._ai_call(q, code, "Correcao de Bug")

    def ai_suggestion(self):
        if not self._ensure_ai():
            return
        code = self.get_current_code()
        if code is None:
            return
        q = simpledialog.askstring("Sugestao", "O que quer melhorar?")
        if q is None:
            return
        self._ai_call("Sugestoes para: " + q, code, "Sugestoes")

    def ai_explain(self):
        code = self.get_current_code()
        if code is None:
            return
        self._ai_call("Explique este codigo em portugues. Seja didatico.",
                      code, "Explicacao")

    def ai_explain_beginner(self):
        was = self.ai.beginner_mode
        self.ai.set_beginner(True)
        try:
            code = self.get_current_code()
            if code is None:
                return
            self._ai_call("Explique este codigo como se eu nunca tivesse usado Lua/GMod. "
                          "Defina termos, use analogias e diga onde colocar.",
                          code, "Explicacao (Iniciante)")
        finally:
            self.ai.set_beginner(was)

    def ai_generate_code(self):
        if not self._ensure_ai():
            return
        desc = simpledialog.askstring("Gerar Codigo",
            "Descreva o que voce quer:\n(ex: um hook que da 100 HP quando o player entra)")
        if not desc:
            return
        prompt = (
            "Gere o codigo Lua para GMod 13 que faz:\n\n" + desc + "\n\n"
            "REGRAS:\n"
            "- Retorne APENAS o codigo dentro de UM bloco ```lua\n"
            "- Adicione comentarios\n"
            "- Diga em qual arquivo/pasta colocar (no topo, como comentario)\n"
        )
        self._ai_call(prompt, "", "Codigo Gerado")

    def ai_translate_comments(self):
        code = self.get_current_code()
        if code is None:
            return
        pt_words = ['que', 'para', 'este', 'esta', 'como', 'faz', 'quando', 'voce']
        en_words = ['this', 'that', 'when', 'the', 'you', 'always', 'player']
        low = code.lower()
        pt_score = sum(1 for w in pt_words if w in low)
        en_score = sum(1 for w in en_words if w in low)
        if pt_score >= en_score:
            target = "ingles"; direction = "PT -> EN"
        else:
            target = "portugues"; direction = "EN -> PT"
        if not messagebox.askyesno("Traduzir", "Traduzir comentarios para " + target + "?"):
            return
        prompt = (
            "Traduza APENAS os comentarios (linhas -- e blocos --[[ ]]) "
            "do codigo abaixo para " + target + ".\n"
            "NAO altere o codigo, apenas comentarios.\n"
            "Retorne o codigo COMPLETO dentro de UM bloco ```lua\n"
        )
        self._ai_call(prompt, code, "Traducao (" + direction + ")")

    def _ai_call(self, prompt, code, title):
        """Helper generico para chamadas de IA."""
        if not self._ensure_ai():
            return

        # Verifica tamanho e avisa se vai truncar
        if code and len(code) > AI_MAX_CODE_CHARS:
            if not self.ai_auto_truncate:
                if not messagebox.askyesno("Codigo Grande",
                    "O codigo tem " + str(len(code)) + " caracteres.\n"
                    "Isso pode exceder o limite da IA.\n\n"
                    "Continuar mesmo assim?"):
                    return
            else:
                pct = int(len(code) * 100 / AI_MAX_CODE_CHARS)
                if not messagebox.askyesno("Codigo Grande",
                    "O codigo tem " + str(len(code)) + " chars (" + str(pct) + "% do limite).\n"
                    "Ele sera TRUNCADO antes de enviar para a IA.\n\n"
                    "O topo e o final serao mantidos.\n\n"
                    "Continuar?"):
                    return

        self.update_status("Pensando... (IA)")

        def worker():
            trunc = self.truncator if self.ai_auto_truncate else None
            r = self.ai.ask(prompt, code, None, trunc)
            def ui():
                if "error" in r:
                    messagebox.showerror("Erro", r['error'])
                    self.update_status("Erro IA")
                    return
                content = r['answer']
                if r.get('truncated'):
                    content += ("\n\n---\n[NOTA: o codigo foi truncado antes de enviar "
                                "(" + str(r.get('lines_removed', 0)) + " linhas removidas)]")
                self.show_ai_result(content, title)
            self.root.after(0, ui)

        threading.Thread(target=worker, daemon=True).start()

    def show_ai_result(self, content, title):
        t = self.theme
        w = tk.Toplevel(self.root)
        w.title("IA - " + title)
        w.geometry("750x560")
        w.transient(self.root)
        w.grab_set()
        w.config(bg=t['bg'])
        f = ttk.Frame(w, padding="10")
        f.pack(fill=tk.BOTH, expand=True)
        hdr = ttk.Frame(f)
        hdr.pack(fill=tk.X)
        dark = (t['icon_mode'] == 'dark')
        photo = self.icons.get('ai', 24, dark=dark) if self.icons_enabled else None
        if photo:
            ttk.Label(hdr, image=photo).pack(side=tk.LEFT, padx=(0, 6))
            w._ai_icon = photo
        ttk.Label(hdr, text=title, font=("Arial", 12, "bold")).pack(side=tk.LEFT)
        ttk.Separator(f, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=5)
        tf = ttk.Frame(f)
        tf.pack(fill=tk.BOTH, expand=True)
        tbox = tk.Text(tf, wrap=tk.WORD, font=("Consolas", 10),
                       bg=t['bg'], fg=t['fg'], insertbackground=t['insert'],
                       selectbackground=t['select_bg'])
        tbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sy = ttk.Scrollbar(tf, orient=tk.VERTICAL, command=tbox.yview)
        sy.pack(side=tk.RIGHT, fill=tk.Y)
        tbox.config(yscrollcommand=sy.set)
        tbox.insert('1.0', content)

        bf = ttk.Frame(f)
        bf.pack(fill=tk.X, pady=10)

        def copy_all():
            try:
                w.clipboard_clear(); w.clipboard_append(content); w.update()
                self.update_status("Copiado")
            except Exception:
                pass

        def insert_as_new_tab():
            if not self.project_path:
                messagebox.showinfo("Info", "Abra um projeto primeiro.")
                return
            matches = re.findall(r'```lua\n(.*?)\n```', content, re.DOTALL)
            if not matches:
                matches = re.findall(r'```lua\n(.*?)```', content, re.DOTALL)
            if not matches:
                messagebox.showinfo("Info", "Nao achei bloco lua.")
                return
            code = max(matches, key=len).rstrip('\n')
            name = simpledialog.askstring("Novo arquivo", "Nome:")
            if not name:
                return
            name = sanitize_name(name)
            if not name.endswith('.lua'):
                name += '.lua'
            fp = os.path.join(self.project_path, 'lua', name)
            os.makedirs(os.path.dirname(fp), exist_ok=True)
            try:
                with open(fp, 'w', encoding='utf-8') as f:
                    f.write(code)
                self.refresh_explorer()
                self.add_tab(fp)
                self.update_status("Criado: " + name)
                w.destroy()
            except Exception as e:
                messagebox.showerror("Erro", str(e))

        ttk.Button(bf, text="Copiar", command=copy_all).pack(side=tk.LEFT, padx=3)
        ttk.Button(bf, text="Aplicar no Editor",
                   command=lambda: self.apply_ai_fix(content, w)).pack(side=tk.LEFT, padx=3)
        ttk.Button(bf, text="Salvar como Novo Arquivo",
                   command=insert_as_new_tab).pack(side=tk.LEFT, padx=3)
        ttk.Button(bf, text="Fechar", command=w.destroy).pack(side=tk.RIGHT, padx=3)

        self.update_status("IA respondeu!")

    def apply_ai_fix(self, content, window):
        if not self.current_tab:
            messagebox.showinfo("Aplicar", "Nenhum arquivo aberto.")
            return
        matches = re.findall(r'```lua\n(.*?)\n```', content, re.DOTALL)
        if not matches:
            matches = re.findall(r'```lua\n(.*?)```', content, re.DOTALL)
        if not matches:
            messagebox.showinfo("Aviso", "Sem bloco lua na resposta.")
            return
        code = max(matches, key=len).rstrip('\n')
        if messagebox.askyesno("Aplicar", "Substituir o codigo atual?"):
            self.current_tab.delete('1.0', tk.END)
            self.current_tab.insert('1.0', code)
            LuaHighlighter.apply(self.current_tab, self.theme)
            self._schedule_lint(self.current_tab_path)
            window.destroy()
            self.update_status("Aplicado!")

    # =========================================
    # GIT
    # =========================================

    def _ensure_repo_path(self):
        if not self.project_path:
            messagebox.showinfo("Git", "Abra um projeto primeiro.")
            return False
        self.git.set_repo(self.project_path)
        return True

    def _show_output(self, title, content):
        t = self.theme
        w = tk.Toplevel(self.root)
        w.title(title)
        w.geometry("700x500")
        w.transient(self.root)
        w.config(bg=t['bg'])
        f = ttk.Frame(w, padding="10")
        f.pack(fill=tk.BOTH, expand=True)
        ttk.Label(f, text=title, font=("Arial", 12, "bold")).pack(anchor=tk.W)
        ttk.Separator(f, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=5)
        tf = ttk.Frame(f); tf.pack(fill=tk.BOTH, expand=True)
        txt = tk.Text(tf, wrap=tk.WORD, font=("Consolas", 9), bg=t['bg'], fg=t['fg'])
        txt.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb = ttk.Scrollbar(tf, orient=tk.VERTICAL, command=txt.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        txt.config(yscrollcommand=sb.set)
        txt.insert('1.0', content)
        txt.config(state='disabled')
        ttk.Button(f, text="Fechar", command=w.destroy).pack(pady=5)

    def git_status(self):
        if not self._ensure_repo_path():
            return
        if not self.git.available:
            messagebox.showerror("Git", "Git nao instalado.\nhttps://git-scm.com/download/win")
            return
        if not self.git.is_repo():
            if messagebox.askyesno("Git", "Nao e um repo. Inicializar?"):
                self.git_init()
            return
        ok, out, err = self.git.status()
        if ok:
            self._show_output("Git Status", out or "Nada para commitar.")
        else:
            messagebox.showerror("Git", err or "Erro.")

    def git_init(self):
        if not self._ensure_repo_path():
            return
        ok, out, err = self.git.init()
        if ok:
            messagebox.showinfo("Git", "Repositorio inicializado.")
        else:
            messagebox.showerror("Git", err or "Erro.")

    def git_commit_dialog(self):
        if not self._ensure_repo_path():
            return
        if not self.git.available or not self.git.is_repo():
            messagebox.showerror("Git", "Git nao disponivel.")
            return
        msg = simpledialog.askstring("Commit", "Mensagem:")
        if not msg:
            return
        ok1, out1, err1 = self.git.add_all()
        if not ok1:
            messagebox.showerror("Git", "Erro add:\n" + (err1 or out1))
            return
        ok2, out2, err2 = self.git.commit(msg)
        if ok2:
            self.update_status("Commit feito")
            self._show_output("Commit", out2)
        else:
            messagebox.showerror("Git", "Erro commit:\n" + (err2 or out2))

    def git_push_dialog(self):
        if not self._ensure_repo_path():
            return
        if not self.git.available or not self.git.is_repo():
            messagebox.showerror("Git", "Git nao disponivel.")
            return
        remote = self.config.get('git_remote', 'origin')
        branch = self.git.current_branch()
        ok, out, err = self.git.push(remote, branch)
        if ok:
            self.update_status("Push feito")
            self._show_output("Push", out)
        else:
            messagebox.showerror("Git", "Erro push:\n" + (err or out))

    def git_pull_dialog(self):
        if not self._ensure_repo_path():
            return
        if not self.git.available or not self.git.is_repo():
            messagebox.showerror("Git", "Git nao disponivel.")
            return
        remote = self.config.get('git_remote', 'origin')
        branch = self.git.current_branch()
        ok, out, err = self.git.pull(remote, branch)
        if ok:
            self.update_status("Pull feito")
            self._show_output("Pull", out)
        else:
            messagebox.showerror("Git", "Erro pull:\n" + (err or out))

    def git_log(self):
        if not self._ensure_repo_path():
            return
        if not self.git.available or not self.git.is_repo():
            messagebox.showerror("Git", "Git nao disponivel.")
            return
        ok, out, err = self.git.log_last(10)
        if ok:
            self._show_output("Commits", out)
        else:
            messagebox.showerror("Git", err or "Erro.")

    def git_open_terminal(self):
        if not self._ensure_repo_path():
            return
        try:
            os.startfile(self.project_path)
        except Exception as e:
            messagebox.showerror("Erro", str(e))

    # =========================================
    # SNIPPETS
    # =========================================

    def save_selection_as_snippet(self):
        if not self.current_tab:
            messagebox.showinfo("Snippet", "Nenhum arquivo aberto.")
            return
        try:
            code = self.current_tab.get(tk.SEL_FIRST, tk.SEL_LAST)
        except tk.TclError:
            messagebox.showinfo("Snippet", "Selecione um trecho primeiro.")
            return
        if not code.strip():
            return
        name = simpledialog.askstring("Salvar Snippet", "Nome:")
        if not name:
            return
        ok, msg = self.snippet_manager.save(name, code)
        if ok:
            self.update_status("Snippet salvo")
            self._refresh_create_menu()
            messagebox.showinfo("Snippet", "Salvo!")
        else:
            messagebox.showerror("Snippet", "Erro: " + msg)

    def insert_snippet(self, snippet):
        if not self.current_tab:
            messagebox.showinfo("Snippet", "Abra um .lua primeiro.")
            return
        try:
            self.current_tab.insert(tk.INSERT, snippet['code'])
            self.update_status("Snippet: " + snippet['name'])
        except Exception as e:
            messagebox.showerror("Erro", str(e))

    def open_snippets_folder(self):
        try:
            os.makedirs(self.snippet_manager.snippets_dir, exist_ok=True)
            os.startfile(self.snippet_manager.snippets_dir)
        except Exception as e:
            messagebox.showerror("Erro", str(e))

    def open_snippets_manager(self):
        t = self.theme
        w = tk.Toplevel(self.root)
        w.title("Snippets")
        w.geometry("650x480")
        w.transient(self.root)
        w.config(bg=t['bg'])
        f = ttk.Frame(w, padding="10")
        f.pack(fill=tk.BOTH, expand=True)
        ttk.Label(f, text="Snippets", font=("Arial", 12, "bold")).pack(anchor=tk.W)
        ttk.Label(f, text=self.snippet_manager.snippets_dir,
                  font=("Arial", 8)).pack(anchor=tk.W)
        ttk.Separator(f, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=5)
        tv = ttk.Treeview(f, columns=('name', 'type'), show='headings', height=12)
        tv.heading('name', text='Nome')
        tv.heading('type', text='Tipo')
        tv.column('name', width=400)
        tv.column('type', width=120)
        tv.pack(fill=tk.BOTH, expand=True, pady=5)
        sv = ttk.Scrollbar(f, orient=tk.VERTICAL, command=tv.yview)
        sv.pack(side=tk.RIGHT, fill=tk.Y)
        tv.config(yscrollcommand=sv.set)
        preview = tk.Text(f, height=8, wrap=tk.WORD, font=("Consolas", 9),
                          bg=t['bg'], fg=t['fg'], relief=tk.FLAT)
        preview.pack(fill=tk.X, pady=5)
        preview.config(state='disabled')
        state = {'sel': None}

        def refresh():
            tv.delete(*tv.get_children())
            for s in self.snippet_manager.get_all():
                tv.insert("", "end", iid=s['name'], values=(s['name'], s.get('type', 'lua')))

        def on_sel(event):
            sel = tv.selection()
            if not sel:
                return
            s = self.snippet_manager.snippets.get(sel[0])
            state['sel'] = s
            if s:
                preview.config(state='normal')
                preview.delete('1.0', tk.END)
                preview.insert('1.0', s['code'])
                preview.config(state='disabled')

        tv.bind('<<TreeviewSelect>>', on_sel)

        def del_sel():
            s = state['sel']
            if not s:
                return
            if messagebox.askyesno("Deletar", "Deletar '" + s['name'] + "'?"):
                if self.snippet_manager.delete(s['name']):
                    refresh()
                    self._refresh_create_menu()

        def ins_sel():
            if state['sel']:
                self.insert_snippet(state['sel'])

        bf = ttk.Frame(f)
        bf.pack(fill=tk.X, pady=10)
        ttk.Button(bf, text="Inserir", command=ins_sel).pack(side=tk.LEFT, padx=3)
        ttk.Button(bf, text="Deletar", command=del_sel).pack(side=tk.LEFT, padx=3)
        ttk.Button(bf, text="Recarregar",
                   command=lambda: (self.snippet_manager.reload(), refresh())).pack(side=tk.LEFT, padx=3)
        ttk.Button(bf, text="Fechar", command=w.destroy).pack(side=tk.RIGHT, padx=3)
        refresh()

    # =========================================
    # PLUGINS
    # =========================================

    def reload_plugins(self):
        try:
            self.plugin_manager.reload()
            self._refresh_create_menu()
            self.update_status("Plugins recarregados")
        except Exception as e:
            messagebox.showerror("Erro", str(e))

    def _refresh_create_menu(self):
        try:
            self.create_menu()
        except Exception as e:
            print("refresh menu: " + str(e))

    def open_plugins_folder(self):
        try:
            os.makedirs(self.plugin_manager.plugins_dir, exist_ok=True)
            os.startfile(self.plugin_manager.plugins_dir)
        except Exception as e:
            messagebox.showerror("Erro", str(e))

    def open_available_folder(self):
        try:
            os.makedirs(self.plugin_manager.available_dir, exist_ok=True)
            os.startfile(self.plugin_manager.available_dir)
        except Exception as e:
            messagebox.showerror("Erro", str(e))

    def open_plugins_manager(self):
        t = self.theme
        w = tk.Toplevel(self.root)
        w.title("Gerenciador de Plugins")
        w.geometry("800x560")
        w.transient(self.root)
        w.config(bg=t['bg'])
        f = ttk.Frame(w, padding="10")
        f.pack(fill=tk.BOTH, expand=True)
        ttk.Label(f, text="Plugins instalados", font=("Arial", 12, "bold")).pack(anchor=tk.W)
        ttk.Label(f, text=self.plugin_manager.plugins_dir, font=("Arial", 8)).pack(anchor=tk.W)
        ttk.Separator(f, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=5)

        cols = ('name', 'version', 'status', 'deps')
        tv = ttk.Treeview(f, columns=cols, show='headings', height=10)
        tv.heading('name', text='Nome')
        tv.heading('version', text='Versao')
        tv.heading('status', text='Status')
        tv.heading('deps', text='Requer')
        tv.column('name', width=250)
        tv.column('version', width=70)
        tv.column('status', width=130)
        tv.column('deps', width=280)
        tv.pack(fill=tk.BOTH, expand=True, pady=5)
        sv = ttk.Scrollbar(f, orient=tk.VERTICAL, command=tv.yview)
        sv.pack(side=tk.RIGHT, fill=tk.Y)
        tv.config(yscrollcommand=sv.set)

        ttk.Label(f, text="Descricao:", font=("Arial", 9, "bold")).pack(anchor=tk.W, pady=(5, 0))
        info = tk.Text(f, height=6, wrap=tk.WORD, font=("Consolas", 9),
                       bg=t['bg'], fg=t['fg'], relief=tk.FLAT)
        info.pack(fill=tk.X, pady=5)
        info.config(state='disabled')
        state = {'sel': None}

        def refresh():
            tv.delete(*tv.get_children())
            items = list(self.plugin_manager.plugins.values())
            items.sort(key=lambda p: p.name.lower())
            for p in items:
                if not p.loaded:
                    status = "ERRO"
                elif p.enabled:
                    ok, _ = self.plugin_manager._check_deps(p)
                    status = "ATIVO" if ok else "DEPS FALTANDO"
                else:
                    status = "inativo"
                tv.insert("", "end", iid=p.folder_name,
                          values=(p.name, p.version, status, ", ".join(p.requires) or "-"))

        def on_sel(event):
            sel = tv.selection()
            if not sel:
                return
            p = self.plugin_manager.plugins.get(sel[0])
            state['sel'] = p
            if not p:
                return
            txt = ""
            if not p.loaded:
                txt = "[ERRO]\n" + str(p.error) + "\n"
            else:
                txt = p.description + "\n\n"
                ok, missing = self.plugin_manager._check_deps(p)
                if not ok:
                    txt += "DEPS FALTANDO: " + ", ".join(missing) + "\n"
                txt += "Autocomplete: " + str(len(p.get_autocomplete())) + "\n"
                txt += "Keywords: " + str(len(p.get_keywords())) + "\n"
                txt += "Templates: " + str(len(p.get_templates())) + "\n"
            info.config(state='normal')
            info.delete('1.0', tk.END)
            info.insert('1.0', txt)
            info.config(state='disabled')

        tv.bind('<<TreeviewSelect>>', on_sel)

        def toggle_sel():
            p = state['sel']
            if not p:
                return
            if p.set_enabled(not p.enabled):
                self.plugin_manager.reload()
                refresh()
                self._refresh_create_menu()

        def uninstall_sel():
            p = state['sel']
            if not p:
                return
            if messagebox.askyesno("Desinstalar",
                "Desinstalar '" + p.name + "'?\nVoce pode reinstalar pelo Marketplace."):
                ok, msg = self.plugin_manager.uninstall_plugin(p.folder_name)
                if ok:
                    self.plugin_manager.reload()
                    refresh()
                    self._refresh_create_menu()
                else:
                    messagebox.showerror("Erro", msg)

        bf = ttk.Frame(f)
        bf.pack(fill=tk.X, pady=10)
        ttk.Button(bf, text="Ativar/Desativar", command=toggle_sel).pack(side=tk.LEFT, padx=3)
        ttk.Button(bf, text="Desinstalar", command=uninstall_sel).pack(side=tk.LEFT, padx=3)
        ttk.Button(bf, text="Recarregar",
                   command=lambda: (self.plugin_manager.reload(), refresh())).pack(side=tk.LEFT, padx=3)
        ttk.Button(bf, text="Marketplace",
                   command=self.open_marketplace).pack(side=tk.LEFT, padx=3)
        ttk.Button(bf, text="Fechar", command=w.destroy).pack(side=tk.RIGHT, padx=3)
        refresh()

    def open_marketplace(self):
        t = self.theme
        w = tk.Toplevel(self.root)
        w.title("Marketplace")
        w.geometry("800x560")
        w.transient(self.root)
        w.config(bg=t['bg'])
        f = ttk.Frame(w, padding="10")
        f.pack(fill=tk.BOTH, expand=True)
        ttk.Label(f, text="Marketplace (local)", font=("Arial", 12, "bold")).pack(anchor=tk.W)
        ttk.Label(f, text=self.plugin_manager.available_dir, font=("Arial", 8)).pack(anchor=tk.W)
        ttk.Separator(f, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=5)

        cols = ('name', 'version', 'author', 'status')
        tv = ttk.Treeview(f, columns=cols, show='headings', height=12)
        tv.heading('name', text='Nome')
        tv.heading('version', text='Versao')
        tv.heading('author', text='Autor')
        tv.heading('status', text='Status')
        tv.column('name', width=250); tv.column('version', width=70)
        tv.column('author', width=120); tv.column('status', width=120)
        tv.pack(fill=tk.BOTH, expand=True, pady=5)
        sv = ttk.Scrollbar(f, orient=tk.VERTICAL, command=tv.yview)
        sv.pack(side=tk.RIGHT, fill=tk.Y)
        tv.config(yscrollcommand=sv.set)

        ttk.Label(f, text="Descricao:", font=("Arial", 9, "bold")).pack(anchor=tk.W, pady=(5, 0))
        info = tk.Text(f, height=6, wrap=tk.WORD, font=("Consolas", 9),
                       bg=t['bg'], fg=t['fg'], relief=tk.FLAT)
        info.pack(fill=tk.X, pady=5)
        info.config(state='disabled')
        state = {'items': [], 'sel': None}

        def refresh():
            tv.delete(*tv.get_children())
            state['items'] = self.plugin_manager.list_available()
            for item in state['items']:
                meta = item['meta']
                status = "INSTALADO" if item['installed'] else "disponivel"
                tv.insert("", "end", iid=item['folder'],
                          values=(meta.get('name', item['folder']),
                                  meta.get('version', '?'),
                                  meta.get('author', '?'), status))

        def on_sel(event):
            sel = tv.selection()
            if not sel:
                return
            folder = sel[0]
            for item in state['items']:
                if item['folder'] == folder:
                    state['sel'] = item
                    meta = item['meta']
                    txt = meta.get('description', '') + "\n\n"
                    req = meta.get('requires', [])
                    if req:
                        txt += "Requer: " + ", ".join(req) + "\n"
                    txt += "Instalado: " + ("sim" if item['installed'] else "nao") + "\n"
                    info.config(state='normal')
                    info.delete('1.0', tk.END)
                    info.insert('1.0', txt)
                    info.config(state='disabled')
                    break

        tv.bind('<<TreeviewSelect>>', on_sel)

        def install_sel():
            item = state['sel']
            if not item:
                messagebox.showinfo("Info", "Selecione um plugin.")
                return
            if item['installed']:
                messagebox.showinfo("Info", "Ja instalado.")
                return
            ok, msg = self.plugin_manager.install_plugin(item['folder'])
            if ok:
                self.plugin_manager.reload()
                refresh()
                self._refresh_create_menu()
                self.update_status("Instalado: " + item['meta'].get('name', item['folder']))
                messagebox.showinfo("Sucesso", "Plugin instalado!")
            else:
                messagebox.showerror("Erro", msg)

        bf = ttk.Frame(f)
        bf.pack(fill=tk.X, pady=10)
        ttk.Button(bf, text="Instalar", command=install_sel).pack(side=tk.LEFT, padx=3)
        ttk.Button(bf, text="Recarregar",
                   command=lambda: (self.plugin_manager.reload(), refresh())).pack(side=tk.LEFT, padx=3)
        ttk.Button(bf, text="Fechar", command=w.destroy).pack(side=tk.RIGHT, padx=3)
        refresh()

    def create_example_plugin_wizard(self):
        name = simpledialog.askstring("Criar Plugin", "Nome (sem espacos):")
        if not name:
            return
        folder = sanitize_name(name).lower().replace(' ', '_')
        if not folder:
            return
        full = os.path.join(self.plugin_manager.plugins_dir, folder)
        if os.path.exists(full):
            messagebox.showerror("Erro", "Ja existe.")
            return
        metadata = {
            "name": name, "version": "1.0.0", "author": "Seu Nome",
            "description": "Plugin criado pelo editor",
            "enabled": True, "requires": [],
            "autocomplete": [["minhaFunc", "minhaFunc()", "Faz algo"]],
            "keywords": [], "templates": []
        }
        try:
            os.makedirs(full, exist_ok=True)
            with open(os.path.join(full, "plugin.json"), 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=4, ensure_ascii=False)
            self.plugin_manager.reload()
            self._refresh_create_menu()
            messagebox.showinfo("Sucesso", "Criado em:\n" + full)
            try:
                os.startfile(full)
            except Exception:
                pass
        except Exception as e:
            messagebox.showerror("Erro", str(e))

    # =========================================
    # TEMPLATE FROM PLUGIN
    # =========================================

    def create_from_plugin_template(self, template_info, target_item=None):
        if not self.project_path:
            messagebox.showerror("Erro", "Abra um projeto!")
            return
        ttype = template_info.get('type', 'lua')
        label = template_info.get('label', 'template')
        script = template_info.get('script', '')
        name = simpledialog.askstring("Criar " + label, "Nome:")
        if not name:
            return
        name = sanitize_name(name)
        if not name:
            return
        dest = None
        if target_item:
            d = self.get_item_path(target_item)
            if d:
                if os.path.isfile(d):
                    d = os.path.dirname(d)
                if os.path.isdir(d):
                    dest = d
        if not dest:
            if ttype == "swep":
                dest = os.path.join(self.project_path, "lua", "weapons")
            elif ttype == "entity":
                dest = os.path.join(self.project_path, "lua", "entities", name)
            else:
                dest = os.path.join(self.project_path, "lua")
        os.makedirs(dest, exist_ok=True)
        if ttype == "swep":
            mf = os.path.join(dest, "weapon_" + name.lower() + ".lua")
        elif ttype == "entity":
            mf = os.path.join(dest, "shared.lua")
        else:
            mf = os.path.join(dest, name + ".lua")
        if os.path.exists(mf):
            if not messagebox.askyesno("Aviso", "Ja existe. Sobrescrever?"):
                return
        try:
            content = script.replace("{name}", name)
        except Exception:
            content = script
        try:
            with open(mf, 'w', encoding='utf-8') as f:
                f.write(content)
            self.refresh_explorer()
            self.expand_to_path(dest)
            self.add_tab(mf)
            self.update_status("Criado: " + name)
        except Exception as e:
            messagebox.showerror("Erro", str(e))

    # =========================================
    # VPK / BLOCOS
    # =========================================

    def _get_selected_items(self):
        try:
            return list(self.explorer_tree.selection())
        except Exception:
            return []

    def _copy_selected_vpk_multi(self):
        sel = self._get_selected_items()
        if not sel:
            return
        vpks = [self.get_vpk_path(it) for it in sel]
        vpks = [v for v in vpks if v]
        if not vpks:
            return
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append("\n".join(vpks))
            self.root.update()
            self._flash_status("Copiados " + str(len(vpks)) + " VPKs")
        except Exception as e:
            messagebox.showerror("Erro", str(e))

    def copy_folder_vpk(self, item, recursive=True):
        folder = self.get_item_path(item)
        if not folder or not os.path.isdir(folder):
            return
        vpks = []
        try:
            if recursive:
                for root, _, files in os.walk(folder):
                    for f in files:
                        v = self._vpk_for_path(os.path.join(root, f))
                        if v:
                            vpks.append(v)
            else:
                for f in sorted(os.listdir(folder)):
                    full = os.path.join(folder, f)
                    if os.path.isfile(full):
                        v = self._vpk_for_path(full)
                        if v:
                            vpks.append(v)
        except Exception as e:
            messagebox.showerror("Erro", str(e))
            return
        if not vpks:
            messagebox.showinfo("Vazio", "Nenhum arquivo.")
            return
        vpks.sort()
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append("\n".join(vpks))
            self.root.update()
            self._flash_status("Copiados " + str(len(vpks)) + " VPKs")
        except Exception as e:
            messagebox.showerror("Erro", str(e))

    def _vpk_for_path(self, full_path):
        if not self.project_path:
            return None
        try:
            return os.path.relpath(full_path, self.project_path).replace(os.sep, '/')
        except Exception:
            return None

    def copy_as_lua_block(self, item, kind):
        p = self.get_item_path(item)
        if not p:
            return
        vpk = self.get_vpk_path(item) or os.path.basename(p)
        if kind == "material": snippet = 'local mat = Material("' + vpk + '")'
        elif kind == "sound": snippet = 'local snd = Sound("' + vpk + '")'
        elif kind == "emit": snippet = 'self:EmitSound("' + vpk + '")'
        elif kind == "model": snippet = 'self:SetModel("' + vpk + '")'
        elif kind == "resource_add": snippet = 'resource.AddFile("' + vpk + '")'
        elif kind == "path_only": snippet = '"' + vpk + '"'
        else: snippet = vpk
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(snippet)
            self.root.update()
            self._flash_status("Copiado")
        except Exception as e:
            messagebox.showerror("Erro", str(e))

    def get_current_code(self):
        if not self.current_tab or not self.current_tab_path:
            messagebox.showwarning("IA", "Abra um arquivo .lua primeiro.")
            return None
        if self.current_tab_path not in self.open_tabs:
            return None
        return self.current_tab.get('1.0', tk.END).rstrip('\n')

    def _ensure_ai(self):
        if not GROQ_AVAILABLE:
            messagebox.showerror("Erro", "Groq nao instalado!\npy -m pip install groq")
            return False
        if not self.ai.is_ready():
            if not messagebox.askyesno("API Key", "Configurar agora?"):
                return False
            self.open_settings()
            return False
        return True

    def format_current_code(self):
        if not self.current_tab:
            messagebox.showerror("Erro", "Nenhum arquivo aberto!")
            return
        try:
            code = self.current_tab.get('1.0', tk.END).rstrip('\n')
            formatted = LuaFormatter.format(code)
            self.current_tab.delete('1.0', tk.END)
            self.current_tab.insert('1.0', formatted)
            LuaHighlighter.apply(self.current_tab, self.theme)
            self.update_status("Formatado!")
        except Exception as e:
            messagebox.showerror("Erro", str(e))

    # =========================================
    # LAYOUT
    # =========================================

    def create_main_layout(self):
        t = self.theme
        self.main_panel = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        self.main_panel.pack(fill=tk.BOTH, expand=True)

        self.left_frame = ttk.Frame(self.main_panel, width=280)
        self.main_panel.add(self.left_frame, weight=1)
        hd = ttk.Frame(self.left_frame)
        hd.pack(fill=tk.X, pady=2)
        dark = (t['icon_mode'] == 'dark')
        pf = self.icons.get('folder', 18, dark=dark) if self.icons_enabled else None
        if pf:
            lbl = ttk.Label(hd, image=pf)
            lbl.pack(side=tk.LEFT, padx=(5, 2))
            hd._icon = pf
        ttk.Label(hd, text="EXPLORADOR", font=("Arial", 9, "bold"),
                  foreground=t['fg_dim']).pack(side=tk.LEFT)
        btn_rf = ttk.Button(hd, command=self.refresh_explorer, width=3)
        rp = self.icons.get('refresh', 16, dark=dark) if self.icons_enabled else None
        if rp:
            btn_rf.config(image=rp); btn_rf._icon = rp
        else:
            btn_rf.config(text="R")
        btn_rf.pack(side=tk.RIGHT)

        self.explorer_tree = ttk.Treeview(self.left_frame, selectmode='extended')
        self.explorer_tree.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        sy = ttk.Scrollbar(self.left_frame, orient=tk.VERTICAL,
                           command=self.explorer_tree.yview)
        sy.pack(side=tk.RIGHT, fill=tk.Y)
        self.explorer_tree.configure(yscrollcommand=sy.set)
        self.explorer_tree.bind("<Button-3>", self.show_explorer_context_menu)
        self.explorer_tree.bind("<Double-1>", self.open_file_from_explorer)

        self.center_frame = ttk.Frame(self.main_panel)
        self.main_panel.add(self.center_frame, weight=4)
        self.tab_header = ttk.Frame(self.center_frame, height=30)
        self.tab_header.pack(fill=tk.X)
        self.tab_header.pack_propagate(False)
        self.tab_canvas = tk.Canvas(self.tab_header, height=28, highlightthickness=0,
                                    bg=t['bg_panel'])
        self.tab_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.tabs_frame = ttk.Frame(self.tab_canvas)
        self.tab_canvas.create_window((0, 0), window=self.tabs_frame, anchor=tk.NW)
        tab_scroll = ttk.Scrollbar(self.tab_header, orient=tk.HORIZONTAL,
                                    command=self.tab_canvas.xview)
        tab_scroll.pack(side=tk.BOTTOM, fill=tk.X)
        self.tab_canvas.configure(xscrollcommand=tab_scroll.set)

        self.editor_frame = ttk.Frame(self.center_frame)
        self.editor_frame.pack(fill=tk.BOTH, expand=True)
        self.placeholder = ttk.Frame(self.editor_frame)
        self.placeholder.pack(fill=tk.BOTH, expand=True)
        ph_inner = ttk.Frame(self.placeholder)
        ph_inner.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
        photo_file = self.icons.get('file_lua', 48, dark=dark) if self.icons_enabled else None
        if photo_file:
            ttk.Label(ph_inner, image=photo_file).pack(pady=5)
            self.placeholder._icon = photo_file
        else:
            ttk.Label(ph_inner, text="Lua", font=("Arial", 32)).pack()
        ttk.Label(ph_inner, text="Nenhum arquivo aberto",
                  font=("Arial", 14), foreground=t['fg_dim']).pack()
        ttk.Label(ph_inner, text="Clique em um arquivo no explorador",
                  font=("Arial", 10), foreground=t['fg_dim']).pack()

        self.current_editor_frame = self.placeholder
        self.tab_buttons = {}

        self.right_frame = ttk.Frame(self.main_panel, width=280)
        self.main_panel.add(self.right_frame, weight=1)
        ph = ttk.Frame(self.right_frame)
        ph.pack(fill=tk.X, pady=2)
        ttk.Label(ph, text="PROPRIEDADES", font=("Arial", 9, "bold"),
                  foreground=t['fg_dim']).pack(side=tk.LEFT, padx=5)
        self.props_canvas = tk.Canvas(self.right_frame, highlightthickness=0)
        self.props_canvas.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        self.props_frame = ttk.Frame(self.props_canvas)
        self.props_canvas.create_window((0, 0), window=self.props_frame, anchor=tk.NW)
        ps = ttk.Scrollbar(self.right_frame, orient=tk.VERTICAL,
                           command=self.props_canvas.yview)
        ps.pack(side=tk.RIGHT, fill=tk.Y)
        self.props_canvas.configure(yscrollcommand=ps.set)
        self.props_frame.bind("<Configure>",
            lambda e: self.props_canvas.configure(scrollregion=self.props_canvas.bbox("all")))
        ttk.Label(self.props_frame, text="Selecione um projeto",
                  font=("Arial", 10), foreground=t['fg_dim']).pack(pady=20)

    def create_status_bar(self):
        sb = ttk.Frame(self.root)
        sb.pack(side=tk.BOTTOM, fill=tk.X)
        self.status_label = ttk.Label(sb, text="Pronto!", relief=tk.SUNKEN, anchor=tk.W)
        self.status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.git_status_label = ttk.Label(sb, text="", relief=tk.SUNKEN, foreground="#c586c0")
        self.git_status_label.pack(side=tk.RIGHT, padx=2)
        self.plugins_status = ttk.Label(sb, text="", relief=tk.SUNKEN, foreground="#4ec9b0")
        self.plugins_status.pack(side=tk.RIGHT, padx=2)
        self.status_project = ttk.Label(sb, text="Nenhum projeto", relief=tk.SUNKEN)
        self.status_project.pack(side=tk.RIGHT, padx=2)
        self.lint_status = ttk.Label(sb, text="", relief=tk.SUNKEN, foreground="#f48771")
        self.lint_status.pack(side=tk.RIGHT, padx=2)
        self.tokens_status = ttk.Label(sb, text="", relief=tk.SUNKEN, foreground="#dcdcaa")
        self.tokens_status.pack(side=tk.RIGHT, padx=2)
        self.tabs_status = ttk.Label(sb, text="0 tabs", relief=tk.SUNKEN, width=8)
        self.tabs_status.pack(side=tk.RIGHT, padx=2)
        self.line_status = ttk.Label(sb, text="Ln 1, Col 1", relief=tk.SUNKEN, width=15)
        self.line_status.pack(side=tk.RIGHT, padx=2)
        self._update_plugins_status()

    def _update_plugins_status(self):
        try:
            n = len(self.plugin_manager.get_enabled())
            total = len(self.plugin_manager.plugins)
            self.plugins_status.config(text="Plugins: " + str(n) + "/" + str(total))
        except Exception:
            pass

    def _update_git_status(self):
        try:
            if self.project_path and self.git.available:
                self.git.set_repo(self.project_path)
                self.git_status_label.config(
                    text="Git: OK" if self.git.is_repo() else "Git: nao init")
            else:
                self.git_status_label.config(text="")
        except Exception:
            pass

    def _update_tokens_status(self):
        """Mostra o tamanho do codigo atual no status bar."""
        try:
            if not self.current_tab:
                self.tokens_status.config(text="")
                return
            code = self.current_tab.get('1.0', tk.END)
            chars = len(code)
            tokens = CodeTruncator.estimate_tokens(code)
            # Cor de acordo com o uso
            pct = chars * 100 / AI_MAX_CODE_CHARS if AI_MAX_CODE_CHARS else 0
            if pct > 100:
                color = "#f48771"
            elif pct > 80:
                color = "#dcdcaa"
            else:
                color = "#4ec9b0"
            self.tokens_status.config(
                text="~" + str(tokens) + " tk",
                foreground=color)
        except Exception:
            pass

    def update_status(self, text, project="", compile_text="", line=""):
        self.status_label.config(text=text)
        if project:
            self.status_project.config(text=project)
        elif self.current_project:
            self.status_project.config(text=self.current_project)
        else:
            self.status_project.config(text="Nenhum projeto")
        if line:
            self.line_status.config(text=line)
        try:
            self.tabs_status.config(text=str(len(self.open_tabs)) + " tabs")
        except Exception:
            pass
        self._update_plugins_status()
        self._update_tokens_status()
        try:
            self.root.update_idletasks()
        except Exception:
            pass

    def _flash_status(self, text, duration_ms=2000):
        try:
            self.status_label.config(text=text, foreground="#4ec9b0")
        except Exception:
            pass
        def _restore():
            try:
                self.status_label.config(foreground=self.theme['fg'])
            except Exception:
                pass
        self.root.after(duration_ms, _restore)

    # =========================================
    # EXPLORER
    # =========================================

    def refresh_explorer(self):
        if self.project_path:
            self.path_to_item = {}
            self.load_explorer(self.project_path)
            self.check_open_tabs()
            self.git.set_repo(self.project_path)
            self._update_git_status()

    def check_open_tabs(self):
        to_close = [p for p in self.open_tabs if not os.path.exists(p)]
        for p in to_close:
            self.close_tab(p)

    def _icon_for_file(self, filename):
        ext = os.path.splitext(filename)[1].lower()
        low = filename.lower()
        if low.startswith('weapon'): return 'swep'
        if ext == '.lua': return 'file_lua'
        if ext == '.txt': return 'file_txt'
        if ext in ('.png', '.jpg', '.jpeg', '.tga', '.vmt', '.vtf', '.bmp', '.gif', '.webp'):
            return 'file_img'
        if ext in ('.mdl', '.vvd', '.vtx', '.phy'): return 'file_mdl'
        if ext in ('.wav', '.mp3', '.ogg'): return 'file_snd'
        return 'file_txt'

    def load_explorer(self, path):
        self.explorer_tree.delete(*self.explorer_tree.get_children())
        self.path_to_item = {}
        dark = (self.theme['icon_mode'] == 'dark')
        if self.icons_enabled:
            mapping = {
                'folder': self.icons.get('folder', 16, dark=dark),
                'folder_open': self.icons.get('folder_open', 16, dark=dark),
                'file_lua': self.icons.get('file_lua', 16, dark=dark),
                'file_txt': self.icons.get('file_txt', 16, dark=dark),
                'file_img': self.icons.get('file_img', 16, dark=dark),
                'file_mdl': self.icons.get('file_mdl', 16, dark=dark),
                'file_snd': self.icons.get('file_snd', 16, dark=dark),
                'swep': self.icons.get('swep', 16, dark=dark),
            }
            for tag, photo in mapping.items():
                if photo:
                    self.explorer_tree.tag_configure(tag, image=photo)
        root_item = self.explorer_tree.insert(
            "", "end", text=" " + os.path.basename(path),
            open=True, tags=('folder_open',))
        self.path_to_item[path] = root_item
        self.add_folder_to_tree(path, root_item)

    def add_folder_to_tree(self, path, parent):
        try:
            for item in sorted(os.listdir(path)):
                if item.startswith('.') or item == 'project.json':
                    continue
                ip = os.path.join(path, item)
                if os.path.isdir(ip):
                    n = self.explorer_tree.insert(parent, "end",
                                                  text=" " + item, open=False,
                                                  tags=('folder',))
                    self.path_to_item[ip] = n
                    self.add_folder_to_tree(ip, n)
                else:
                    tag = self._icon_for_file(item) if self.icons_enabled else 'file'
                    n = self.explorer_tree.insert(parent, "end",
                                                  text=" " + item, tags=(tag,))
                    self.path_to_item[ip] = n
        except PermissionError:
            pass

    def get_item_path(self, item):
        if not self.project_path:
            return None
        for p, ti in self.path_to_item.items():
            if ti == item:
                return p
        parts = []
        cur = item
        while cur:
            parts.insert(0, self.explorer_tree.item(cur, 'text').strip())
            cur = self.explorer_tree.parent(cur)
        if not parts:
            return None
        if len(parts) > 1:
            return os.path.join(self.project_path, *parts[1:])
        return self.project_path

    def get_vpk_path(self, item):
        p = self.get_item_path(item)
        if not p or not self.project_path:
            return None
        try:
            return os.path.relpath(p, self.project_path).replace(os.sep, '/')
        except Exception:
            return None

    def copy_vpk_path(self, item):
        vpk = self.get_vpk_path(item)
        if not vpk:
            messagebox.showerror("Erro", "Nao foi possivel obter.")
            return
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(vpk)
            self.root.update()
            self._flash_status("Copiado: " + vpk)
        except Exception as e:
            messagebox.showerror("Erro", str(e))

    def expand_to_path(self, path):
        if not path or not self.project_path:
            return
        rel = os.path.relpath(path, self.project_path)
        if rel == '.':
            return
        cur = self.project_path
        for part in rel.split(os.sep):
            if not part:
                continue
            cur = os.path.join(cur, part)
            it = self.path_to_item.get(cur)
            if it:
                self.explorer_tree.item(it, open=True)
                self.explorer_tree.item(it, tags=('folder_open',))

    # =========================================
    # TABS
    # =========================================

    def add_tab(self, file_path):
        if file_path in self.open_tabs:
            self.select_tab(file_path)
            return
        t = self.theme
        if self.current_editor_frame == self.placeholder:
            self.placeholder.pack_forget()
        ef = ttk.Frame(self.editor_frame)
        ef.pack(fill=tk.BOTH, expand=True)
        inner = ttk.Frame(ef)
        inner.pack(fill=tk.BOTH, expand=True)
        ln = tk.Text(inner, width=4, padx=4, takefocus=0, border=0,
                     background=t['line_bg'], foreground=t['line_fg'],
                     state='disabled', wrap='none', font=('Consolas', 10))
        ln.pack(side=tk.LEFT, fill=tk.Y)
        tw = tk.Text(inner, wrap='none', font=('Consolas', 10), undo=True,
                     bg=t['bg'], fg=t['fg'], insertbackground=t['insert'],
                     selectbackground=t['select_bg'])
        tw.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sy = ttk.Scrollbar(ef, orient=tk.VERTICAL, command=tw.yview)
        sy.pack(side=tk.RIGHT, fill=tk.Y)
        def _ys(*a):
            tw.yview(*a); ln.yview(*a)
        tw.config(yscrollcommand=sy.set)
        sy.config(command=_ys)
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    tw.insert('1.0', f.read())
                self.file_mtimes[file_path] = os.path.getmtime(file_path)
            except Exception as e:
                print("abrir: " + str(e))
        self.open_tabs[file_path] = (ef, tw, ln)
        self.current_tab = tw
        self.current_tab_path = file_path
        btn = self.create_tab_button(file_path)
        self.tab_buttons[file_path] = btn
        self.update_tab_scroll()
        self.select_tab(file_path)
        tw.bind('<KeyRelease>', lambda e: self._on_text_change(file_path))
        tw.bind('<Button-1>', lambda e: self.select_tab(file_path))
        tw.bind('<MouseWheel>', lambda e: self._on_mousewheel(file_path))
        if self.autocomplete_enabled:
            try:
                self.autocomplete.attach(tw)
                self._ac_installed[file_path] = True
            except Exception:
                pass
        self._update_line_numbers(file_path)
        self._update_line_status(file_path)
        LuaHighlighter.apply(tw, t)
        self.update_status(os.path.basename(file_path))
        self._schedule_lint(file_path)

    def _on_mousewheel(self, file_path):
        self._update_line_numbers(file_path)

    def _on_text_change(self, fp):
        self._update_line_status(fp)
        self._update_line_numbers(fp)
        if self._hl_job:
            try:
                self.root.after_cancel(self._hl_job)
            except Exception:
                pass
            self._hl_job = None
        self._hl_job = self.root.after(250, lambda: self._apply_hl(fp))
        self._schedule_lint(fp)
        self._update_tokens_status()

    def _apply_hl(self, fp):
        self._hl_job = None
        if fp in self.open_tabs:
            try:
                LuaHighlighter.apply(self.open_tabs[fp][1], self.theme)
            except Exception:
                pass

    def _update_line_numbers(self, fp):
        if fp not in self.open_tabs:
            return
        _, tw, ln = self.open_tabs[fp]
        try:
            count = int(tw.index('end-1c').split('.')[0])
            content = '\n'.join(str(i) for i in range(1, count + 1))
            ln.config(state='normal')
            ln.delete('1.0', tk.END)
            ln.insert('1.0', content)
            ln.config(state='disabled')
        except Exception:
            pass

    def create_tab_button(self, file_path):
        t = self.theme
        fr = ttk.Frame(self.tabs_frame)
        fr.pack(side=tk.LEFT, padx=1, pady=1)
        display = truncate_filename(os.path.basename(file_path), 20)
        btn = tk.Label(fr, text=" " + display,
                       font=("Arial", 9), bg=t['tab_bg'], fg=t['tab_fg'],
                       padx=10, pady=2, cursor='hand2')
        btn.pack()
        btn.bind('<Button-1>', lambda e: self.select_tab(file_path))
        btn.bind('<Button-2>', lambda e: self.close_tab(file_path))
        btn.bind('<Button-3>', lambda e: self.close_tab(file_path))
        return btn

    def select_tab(self, file_path):
        if file_path not in self.open_tabs:
            return
        self._check_external_change(file_path)
        t = self.theme
        for p, d in self.open_tabs.items():
            try:
                d[0].pack_forget()
            except Exception:
                pass
        ef, tw, ln = self.open_tabs[file_path]
        ef.pack(fill=tk.BOTH, expand=True)
        self.current_tab = tw
        self.current_tab_path = file_path
        for p, btn in self.tab_buttons.items():
            active = (p == file_path)
            try:
                btn.config(bg=t['tab_bg_active'] if active else t['tab_bg'],
                           fg=t['tab_fg_active'] if active else t['tab_fg'])
            except Exception:
                pass
        self.update_status(os.path.basename(file_path))
        self._update_line_status(file_path)
        try:
            self.autocomplete.hide()
        except Exception:
            pass
        if file_path in self._lint_jobs:
            try:
                self.root.after_cancel(self._lint_jobs[file_path])
            except Exception:
                pass
            del self._lint_jobs[file_path]
        self._run_lint(file_path)
        self._update_tokens_status()

    def _check_external_change(self, file_path):
        if not os.path.exists(file_path):
            return
        try:
            mt = os.path.getmtime(file_path)
        except Exception:
            return
        stored = self.file_mtimes.get(file_path)
        if stored is None:
            self.file_mtimes[file_path] = mt
            return
        if mt <= stored:
            return
        _, tw, _ = self.open_tabs[file_path]
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                disk = f.read()
        except Exception:
            return
        if tw.get('1.0', tk.END).rstrip('\n') == disk.rstrip('\n'):
            self.file_mtimes[file_path] = mt
            return
        self.file_mtimes[file_path] = mt
        if messagebox.askyesno("Modificado",
            "'" + os.path.basename(file_path) + "' mudou. Recarregar?"):
            tw.delete('1.0', tk.END)
            tw.insert('1.0', disk)
            LuaHighlighter.apply(tw, self.theme)
            self._update_line_numbers(file_path)
            self._schedule_lint(file_path)

    def close_tab(self, file_path):
        if file_path not in self.open_tabs:
            return
        ef, tw, _ = self.open_tabs[file_path]
        try:
            cur = tw.get('1.0', tk.END).rstrip('\n')
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    sv = f.read().rstrip('\n')
                if cur != sv and not messagebox.askyesno("Nao salvo",
                    "'" + os.path.basename(file_path) + "' tem alteracoes. Fechar?"):
                    return
        except Exception:
            pass
        try:
            if self._ac_installed.pop(file_path, False):
                self.autocomplete.detach(tw)
        except Exception:
            pass
        if file_path in self._lint_jobs:
            try:
                self.root.after_cancel(self._lint_jobs[file_path])
            except Exception:
                pass
            del self._lint_jobs[file_path]
        try:
            ef.pack_forget()
        except Exception:
            pass
        try:
            ef.destroy()
        except Exception:
            pass
        btn = self.tab_buttons.pop(file_path, None)
        if btn:
            try:
                parent = btn.master
                btn.pack_forget(); btn.destroy()
                parent.pack_forget(); parent.destroy()
            except Exception:
                pass
        del self.open_tabs[file_path]
        if self.current_tab_path == file_path:
            self.current_tab = None
            self.current_tab_path = None
        self._force_tab_redraw()
        if not self.open_tabs:
            self.placeholder.pack(fill=tk.BOTH, expand=True)
            self.update_status("Nenhum arquivo aberto")
            return
        self.select_tab(list(self.open_tabs.keys())[0])

    def _force_tab_redraw(self):
        try:
            self.tabs_frame.update_idletasks()
            self.tab_canvas.update_idletasks()
            bbox = self.tab_canvas.bbox("all")
            if bbox:
                self.tab_canvas.configure(scrollregion=bbox)
            else:
                self.tab_canvas.configure(scrollregion=(0, 0, 0, 0))
            w = self.tab_canvas.winfo_width()
            self.tab_canvas.config(width=w + 1)
            self.tab_canvas.update_idletasks()
            self.tab_canvas.config(width=w)
        except Exception:
            pass

    def update_tab_scroll(self):
        self._force_tab_redraw()

    def close_current_tab(self):
        if self.current_tab_path:
            self.close_tab(self.current_tab_path)

    def cycle_tab(self, d):
        if len(self.open_tabs) < 2:
            return
        paths = list(self.open_tabs.keys())
        try:
            i = paths.index(self.current_tab_path)
        except ValueError:
            i = 0
        self.select_tab(paths[(i + d) % len(paths)])

    def _update_line_status(self, file_path):
        if file_path not in self.open_tabs:
            return
        _, tw, _ = self.open_tabs[file_path]
        try:
            line, col = tw.index(tk.INSERT).split('.')
            self.line_status.config(text="Ln " + line + ", Col " + col)
        except Exception:
            pass

    def open_file_from_explorer(self, event):
        sel = self.explorer_tree.selection()
        if sel:
            self.open_file(sel[0])

    def open_file(self, item):
        p = self.get_item_path(item)
        if not p or not os.path.isfile(p):
            return
        ext = os.path.splitext(p)[1].lower()
        if ext in IMAGE_EXTS:
            self.open_image_viewer(p)
            return
        self.add_tab(p)

    def save_current_tab(self):
        if not self.current_tab_path or self.current_tab_path not in self.open_tabs:
            return
        try:
            _, tw, _ = self.open_tabs[self.current_tab_path]
            with open(self.current_tab_path, 'w', encoding='utf-8') as f:
                f.write(tw.get('1.0', tk.END).rstrip('\n'))
            self.file_mtimes[self.current_tab_path] = os.path.getmtime(self.current_tab_path)
            self.update_status("Salvo: " + os.path.basename(self.current_tab_path))
        except Exception as e:
            messagebox.showerror("Erro", str(e))

    def save_all_tabs(self):
        n = 0
        for fp, data in list(self.open_tabs.items()):
            if fp not in self.open_tabs:
                continue
            try:
                _, tw, _ = data
                with open(fp, 'w', encoding='utf-8') as f:
                    f.write(tw.get('1.0', tk.END).rstrip('\n'))
                self.file_mtimes[fp] = os.path.getmtime(fp)
                n += 1
            except Exception:
                pass
        if n:
            self.update_status(str(n) + " salvo(s)")

    # =========================================
    # IMAGE VIEWER / EXPORT
    # =========================================

    def export_image(self, item=None, source_path=None):
        src = source_path or (self.get_item_path(item) if item else None)
        if not src or not os.path.isfile(src):
            messagebox.showerror("Erro", "Nao encontrado.")
            return
        if not PIL_AVAILABLE:
            messagebox.showerror("Erro", "Pillow nao instalado.")
            return
        base_name = os.path.splitext(os.path.basename(src))[0]
        filtros = [("PNG", "*.png"), ("JPEG", "*.jpg *.jpeg"), ("BMP", "*.bmp"),
                   ("GIF", "*.gif"), ("WebP", "*.webp"), ("TIFF", "*.tiff"), ("Todos", "*.*")]
        dest = filedialog.asksaveasfilename(
            title="Export Image", initialdir=os.path.dirname(src),
            initialfile=base_name + ".png", defaultextension=".png", filetypes=filtros)
        if not dest:
            return
        try:
            img = Image.open(src)
            ext = os.path.splitext(dest)[1].lower()
            out = img
            if ext in ('.jpg', '.jpeg', '.bmp') and img.mode in ('RGBA', 'LA', 'P'):
                out = img.convert('RGB')
            elif ext == '.gif' and img.mode == 'RGBA':
                out = img.convert('P', palette=Image.ADAPTIVE)
            out.save(dest)
            messagebox.showinfo("Sucesso", "Exportado:\n" + dest)
        except Exception as e:
            messagebox.showerror("Erro", str(e))

    def open_image_viewer(self, file_path):
        if not PIL_AVAILABLE or not os.path.exists(file_path):
            return
        try:
            img = Image.open(file_path)
            orig_w, orig_h = img.size
        except Exception as e:
            messagebox.showerror("Erro", str(e))
            return
        max_w = int(self.root.winfo_screenwidth() * 0.7)
        max_h = int(self.root.winfo_screenheight() * 0.7)
        scale = 1.0
        if orig_w > max_w or orig_h > max_h:
            scale = min(max_w / orig_w, max_h / orig_h)
        view_w = max(200, int(orig_w * scale))
        view_h = max(200, int(orig_h * scale))
        w = tk.Toplevel(self.root)
        w.title("Visualizador: " + os.path.basename(file_path))
        w.geometry(str(view_w + 40) + "x" + str(view_h + 100))
        w.transient(self.root)
        w.config(bg=self.theme['bg'])
        state = {'scale': scale, 'photo': None}
        img_frame = tk.Frame(w, bg=self.theme['bg'])
        img_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        img_label = tk.Label(img_frame, bg=self.theme['bg'])
        img_label.pack(expand=True)
        info_frame = ttk.Frame(w)
        info_frame.pack(fill=tk.X, padx=10)
        ttk.Label(info_frame, text=os.path.basename(file_path) + " - " +
                  str(orig_w) + "x" + str(orig_h)).pack(side=tk.LEFT)
        zoom_label = ttk.Label(info_frame, text="100%", font=("Arial", 9, "bold"))
        zoom_label.pack(side=tk.RIGHT, padx=10)
        def render():
            try:
                sc = state['scale']
                nw = max(1, int(orig_w * sc)); nh = max(1, int(orig_h * sc))
                photo = ImageTk.PhotoImage(img.resize((nw, nh), Image.LANCZOS))
                state['photo'] = photo
                img_label.config(image=photo)
                zoom_label.config(text=str(int(sc * 100)) + "%")
            except Exception:
                pass
        def zi(e=None): state['scale'] = min(state['scale'] * 1.25, 8.0); render()
        def zo(e=None): state['scale'] = max(state['scale'] / 1.25, 0.1); render()
        def zr(e=None):
            s = 1.0
            if orig_w > max_w or orig_h > max_h:
                s = min(max_w / orig_w, max_h / orig_h)
            state['scale'] = s; render()
        bf = ttk.Frame(w); bf.pack(fill=tk.X, padx=10, pady=5)
        ttk.Button(bf, text="+", width=3, command=zi).pack(side=tk.LEFT, padx=2)
        ttk.Button(bf, text="-", width=3, command=zo).pack(side=tk.LEFT, padx=2)
        ttk.Button(bf, text="100%", command=zr).pack(side=tk.LEFT, padx=2)
        ttk.Button(bf, text="Export",
                   command=lambda: self.export_image(source_path=file_path)).pack(side=tk.LEFT, padx=10)
        ttk.Button(bf, text="Fechar", command=w.destroy).pack(side=tk.RIGHT, padx=2)
        w.bind('<Escape>', lambda e: w.destroy())
        render()
        try: w.focus_force()
        except Exception: pass

    # =========================================
    # CONTEXT MENU
    # =========================================

    def show_explorer_context_menu(self, event):
        item = self.explorer_tree.identify_row(event.y)
        if not item:
            return
        current_sel = self._get_selected_items()
        if item not in current_sel:
            self.explorer_tree.selection_set(item)
        sel = self._get_selected_items()
        multi = len(sel) > 1
        p = self.get_item_path(item)
        is_file = p and os.path.isfile(p)
        is_dir = p and os.path.isdir(p)
        ext = os.path.splitext(p)[1].lower() if p else ""
        is_image = is_file and ext in IMAGE_EXTS
        m = tk.Menu(self.root, tearoff=0)
        if multi:
            m.add_command(label="Copiar " + str(len(sel)) + " VPKs",
                          command=self._copy_selected_vpk_multi)
            m.add_separator()
        if is_image:
            m.add_command(label="Abrir no Visualizador",
                          command=lambda: self.open_image_viewer(p))
        else:
            m.add_command(label="Abrir", command=lambda: self.open_file(item))
        if is_file:
            m.add_command(label="Copiar Caminho VPK",
                          command=lambda: self.copy_vpk_path(item))
            if is_image:
                m.add_command(label="Export Image...",
                              command=lambda: self.export_image(item))
            lua_sub = tk.Menu(m, tearoff=0)
            m.add_cascade(label="Copiar como...", menu=lua_sub)
            lua_sub.add_command(label='Apenas path',
                command=lambda: self.copy_as_lua_block(item, "path_only"))
            lua_sub.add_separator()
            lua_sub.add_command(label='Material("...")',
                command=lambda: self.copy_as_lua_block(item, "material"))
            lua_sub.add_command(label='Sound("...")',
                command=lambda: self.copy_as_lua_block(item, "sound"))
            lua_sub.add_command(label='self:EmitSound("...")',
                command=lambda: self.copy_as_lua_block(item, "emit"))
            lua_sub.add_command(label='self:SetModel("...")',
                command=lambda: self.copy_as_lua_block(item, "model"))
            lua_sub.add_separator()
            lua_sub.add_command(label='resource.AddFile("...")',
                command=lambda: self.copy_as_lua_block(item, "resource_add"))
        if is_dir:
            m.add_command(label="Copiar VPKs (pasta)",
                command=lambda: self.copy_folder_vpk(item, recursive=True))
            m.add_command(label="Copiar VPKs (pasta, simples)",
                command=lambda: self.copy_folder_vpk(item, recursive=False))
        m.add_separator()
        m.add_command(label="Renomear", command=lambda: self.rename_item(item))
        m.add_command(label="Deletar", command=lambda: self.delete_item(item))
        m.add_separator()
        m.add_command(label="Abrir no Explorer",
                      command=lambda: self.open_in_explorer(item))
        m.add_separator()
        sub = tk.Menu(m, tearoff=0)
        m.add_cascade(label="Criar", menu=sub)
        self._build_create_menu(sub, target_item=item)
        m.post(event.x_root, event.y_root)

    def rename_item(self, item):
        old = self.explorer_tree.item(item, 'text').strip()
        new = simpledialog.askstring("Renomear", "Novo nome:", initialvalue=old)
        if not new or new == old:
            return
        new = sanitize_name(new)
        if not new:
            return
        p = self.get_item_path(item)
        if not p:
            return
        np = os.path.join(os.path.dirname(p), new)
        try:
            os.rename(p, np)
            self.explorer_tree.item(item, text=" " + new)
            self.path_to_item.pop(p, None)
            self.path_to_item[np] = item
            if p in self.open_tabs:
                if p in self.tab_buttons:
                    try:
                        d = truncate_filename(new, 20)
                        self.tab_buttons[p].config(text=" " + d)
                    except Exception:
                        pass
                self.open_tabs[np] = self.open_tabs.pop(p)
                if self.current_tab_path == p:
                    self.current_tab_path = np
            self.update_status("Renomeado")
        except Exception as e:
            messagebox.showerror("Erro", str(e))

    def delete_item(self, item):
        if not messagebox.askyesno("Confirmar", "Deletar?"):
            return
        p = self.get_item_path(item)
        if not p:
            return
        try:
            if p in self.open_tabs:
                self.close_tab(p)
            if os.path.isdir(p):
                shutil.rmtree(p)
            else:
                os.remove(p)
            self.path_to_item.pop(p, None)
            self.explorer_tree.delete(item)
            self.update_status("Deletado")
        except Exception as e:
            messagebox.showerror("Erro", str(e))

    def open_in_explorer(self, item):
        p = self.get_item_path(item)
        if p and os.path.exists(p):
            if os.path.isfile(p):
                p = os.path.dirname(p)
            try:
                os.startfile(p)
            except Exception:
                pass

    # =========================================
    # CRIAR
    # =========================================

    def create_folder(self, target_item=None):
        if not self.project_path:
            messagebox.showerror("Erro", "Abra um projeto!")
            return
        name = simpledialog.askstring("Criar Pasta", "Nome:")
        if not name:
            return
        name = sanitize_name(name)
        if not name:
            return
        if target_item:
            dest = self.get_item_path(target_item)
            if dest and os.path.isfile(dest):
                dest = os.path.dirname(dest)
            if not dest or not os.path.isdir(dest):
                dest = self.project_path
        else:
            dest = self.project_path
        fp = os.path.join(dest, name)
        if os.path.exists(fp):
            messagebox.showerror("Erro", "Ja existe!")
            return
        try:
            os.makedirs(fp)
            self.refresh_explorer()
            self.expand_to_path(fp)
            self.update_status("Pasta: " + os.path.relpath(fp, self.project_path))
        except Exception as e:
            messagebox.showerror("Erro", str(e))

    def create_file(self, file_type, target_item=None):
        if not self.project_path:
            messagebox.showerror("Erro", "Abra um projeto!")
            return
        name = simpledialog.askstring("Criar", "Nome:")
        if not name:
            return
        name = sanitize_name(name)
        if not name:
            return
        exts = {'lua': '.lua', 'paste': '.txt', 'png': '.png', 'jpg': '.jpg'}
        ext = exts.get(file_type, '.txt')
        full = name if name.endswith(ext) else name + ext
        if target_item:
            dest = self.get_item_path(target_item)
            if dest and os.path.isfile(dest):
                dest = os.path.dirname(dest)
            if not dest or not os.path.isdir(dest):
                dest = self.project_path
        else:
            dest = self.project_path
        fp = os.path.join(dest, full)
        if os.path.exists(fp):
            if not messagebox.askyesno("Aviso", "Ja existe. Sobrescrever?"):
                return
        templates = {
            'lua': "--[[\n    " + name + "\n]]\n\n",
            'paste': "# Script Paste\n",
            'png': '', 'jpg': '',
        }
        try:
            if file_type in ('png', 'jpg'):
                try:
                    from PIL import Image
                    Image.new('RGB', (256, 256), 'white').save(fp)
                except Exception:
                    with open(fp, 'wb'):
                        pass
            else:
                with open(fp, 'w', encoding='utf-8') as f:
                    f.write(templates.get(file_type, ''))
            self.refresh_explorer()
            self.expand_to_path(dest)
            if file_type == 'lua':
                self.add_tab(fp)
            self.update_status("Criado: " + os.path.relpath(fp, self.project_path))
        except Exception as e:
            messagebox.showerror("Erro", str(e))

    def create_from_template(self, template_type, target_item=None):
        if not self.project_path:
            messagebox.showerror("Erro", "Abra um projeto!")
            return
        names = {
            'swep_308': 'SWEP (308 Base)',
            'swep_standalone': 'SWEP (Standalone)',
            'entity_vj': 'ENTITY (VJ Base)',
            'entity_drg': 'ENTITY (DRG Base)',
            'entity_standalone': 'ENTITY (Standalone)',
        }
        tn = names.get(template_type, template_type)
        name = simpledialog.askstring("Criar " + tn, "Nome:")
        if not name:
            return
        name = sanitize_name(name)
        if not name:
            return
        dest_forced = None
        if target_item:
            d = self.get_item_path(target_item)
            if d:
                if os.path.isfile(d):
                    d = os.path.dirname(d)
                if os.path.isdir(d):
                    dest_forced = d
        if 'swep' in template_type:
            dest = dest_forced or os.path.join(self.project_path, "lua", "weapons")
        else:
            dest = dest_forced or os.path.join(self.project_path, "lua", "entities", name)
        os.makedirs(dest, exist_ok=True)
        if 'swep' in template_type:
            mf = os.path.join(dest, "weapon_" + name.lower() + ".lua")
        else:
            mf = os.path.join(dest, "shared.lua")
        if os.path.exists(mf):
            if not messagebox.askyesno("Aviso", "Ja existe. Sobrescrever?"):
                return
        content = TEMPLATES.get(template_type, "").format(name=name)
        try:
            with open(mf, 'w', encoding='utf-8') as f:
                f.write(content)
            if template_type == 'entity_standalone':
                with open(os.path.join(dest, "init.lua"), 'w', encoding='utf-8') as f:
                    f.write(ENTITY_INIT_TEMPLATE.format(name=name))
                with open(os.path.join(dest, "cl_init.lua"), 'w', encoding='utf-8') as f:
                    f.write(ENTITY_CL_INIT_TEMPLATE.format(name=name))
            self.refresh_explorer()
            self.expand_to_path(dest)
            self.add_tab(mf)
            self.update_status(tn + ": " + name)
        except Exception as e:
            messagebox.showerror("Erro", str(e))

    def export_asset(self, target_item=None):
        if not self.project_path:
            messagebox.showerror("Erro", "Abra um projeto!")
            return
        p = self.get_item_path(target_item) if target_item else self.project_path
        if not p:
            return
        ef = filedialog.asksaveasfilename(
            title="Exportar", defaultextension=".zip",
            filetypes=[("ZIP", "*.zip"), ("Todos", "*.*")])
        if not ef:
            return
        try:
            with zipfile.ZipFile(ef, 'w', zipfile.ZIP_DEFLATED) as z:
                if os.path.isdir(p):
                    for root, _, files in os.walk(p):
                        for f in files:
                            fp = os.path.join(root, f)
                            z.write(fp, os.path.relpath(fp, os.path.dirname(p)))
                else:
                    z.write(p, os.path.basename(p))
            self.update_status("Exportado")
            messagebox.showinfo("Sucesso", "Exportado:\n" + ef)
        except Exception as e:
            messagebox.showerror("Erro", str(e))

    # =========================================
    # PROJETOS
    # =========================================

    def new_project(self):
        name = simpledialog.askstring("Novo Projeto", "Nome:")
        if not name:
            return
        name = sanitize_name(name)
        if not name:
            return
        pdir = self.config.get('projects_dir', get_default_projects_dir())
        os.makedirs(pdir, exist_ok=True)
        pp = os.path.join(pdir, name)
        if os.path.exists(pp):
            messagebox.showerror("Erro", "Ja existe!")
            return
        try:
            os.makedirs(pp)
            for sub in ["lua/weapons", "lua/entities", "materials", "models", "sound"]:
                os.makedirs(os.path.join(pp, sub))
            with open(os.path.join(pp, "project.json"), 'w', encoding='utf-8') as f:
                json.dump({
                    'name': name, 'gmod_path': self.gmod_path,
                    'output_path': self.output_path, 'version': VERSION,
                    'created': datetime.now().isoformat()
                }, f, indent=2)
            self.load_project(pp)
            self.update_status("Projeto '" + name + "' criado")
            messagebox.showinfo("Sucesso", "Projeto criado!")
        except Exception as e:
            messagebox.showerror("Erro", str(e))

    def open_project(self):
        pdir = self.config.get('projects_dir', get_default_projects_dir())
        folder = filedialog.askdirectory(title="Projeto", initialdir=pdir)
        if folder:
            self.load_project(folder)

    def load_project(self, project_path):
        if not self._is_valid_project(project_path):
            messagebox.showerror("Erro",
                "Pasta nao e um projeto valido:\n" + project_path)
            return
        self.project_path = project_path
        self.current_project = os.path.basename(project_path)
        for fp in list(self.open_tabs.keys()):
            try:
                self.close_tab(fp)
            except Exception:
                pass
        self.load_explorer(project_path)
        self.load_properties()
        self.git.set_repo(project_path)
        self._update_git_status()
        self.update_status("Projeto: " + self.current_project, self.current_project)
        self.config['last_project'] = project_path
        self.config.save()

    def load_properties(self):
        for w in self.props_frame.winfo_children():
            w.destroy()
        r = 0
        ttk.Label(self.props_frame, text="Propriedades",
                  font=("Arial", 10, "bold")).grid(row=r, column=0, columnspan=2,
                                                    pady=5, sticky=tk.W)
        r += 1
        for label, val in [
            ("Nome:", self.current_project or "(nenhum)"),
            ("Caminho:", (self.project_path or "")[:35] + "..."),
            ("GMod Path:", (self.gmod_path or "(nao definido)")[:35] + "..."),
            ("Output Path:", (self.output_path or "")[:35] + "..."),
        ]:
            ttk.Label(self.props_frame, text=label).grid(row=r, column=0,
                                                          sticky=tk.W, padx=5, pady=2)
            ttk.Label(self.props_frame, text=val, font=("Arial", 8)).grid(row=r, column=1,
                                                                           sticky=tk.W, padx=5, pady=2)
            r += 1
        if self.project_path and os.path.exists(self.project_path):
            ttk.Separator(self.props_frame, orient=tk.HORIZONTAL).grid(row=r, column=0,
                                                                        columnspan=2, sticky=tk.EW, pady=5)
            r += 1
            tf = 0; ts = 0
            for root, _, files in os.walk(self.project_path):
                tf += len(files)
                for f in files:
                    fp = os.path.join(root, f)
                    if os.path.exists(fp):
                        ts += os.path.getsize(fp)
            ttk.Label(self.props_frame, text="Arquivos:").grid(row=r, column=0,
                                                                sticky=tk.W, padx=5, pady=2)
            ttk.Label(self.props_frame, text=str(tf), font=("Arial", 8)).grid(row=r, column=1,
                                                                               sticky=tk.W, padx=5, pady=2)
            r += 1
            ttk.Label(self.props_frame, text="Tamanho:").grid(row=r, column=0,
                                                               sticky=tk.W, padx=5, pady=2)
            ttk.Label(self.props_frame, text=str(round(ts / 1024 / 1024, 2)) + " MB",
                      font=("Arial", 8)).grid(row=r, column=1, sticky=tk.W, padx=5, pady=2)

    # =========================================
    # SETTINGS
    # =========================================

    def open_settings(self):
        w = tk.Toplevel(self.root)
        w.title("Configuracoes")
        w.geometry("650x820")
        w.transient(self.root)
        w.grab_set()
        f = ttk.Frame(w, padding="20")
        f.pack(fill=tk.BOTH, expand=True)
        ttk.Label(f, text="Configuracoes", font=("Arial", 16, "bold")).pack(pady=(0, 20))

        ttk.Label(f, text="Pasta do Garry's Mod:").pack(anchor=tk.W)
        gf = ttk.Frame(f); gf.pack(fill=tk.X, pady=5)
        gv = tk.StringVar(value=self.gmod_path)
        ttk.Entry(gf, textvariable=gv, width=50).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        ttk.Button(gf, text="...", width=3, command=lambda: self._browse(gv)).pack(side=tk.RIGHT)

        ttk.Label(f, text="Pasta de Output:").pack(anchor=tk.W, pady=(10, 0))
        of = ttk.Frame(f); of.pack(fill=tk.X, pady=5)
        ov = tk.StringVar(value=self.output_path)
        ttk.Entry(of, textvariable=ov, width=50).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        ttk.Button(of, text="...", width=3, command=lambda: self._browse(ov)).pack(side=tk.RIGHT)

        ttk.Label(f, text="Groq API Key:").pack(anchor=tk.W, pady=(10, 0))
        af = ttk.Frame(f); af.pack(fill=tk.X, pady=5)
        av = tk.StringVar(value=self.config.get('groq_api_key', ''))
        ae = ttk.Entry(af, textvariable=av, show="*", width=50)
        ae.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        ttk.Button(af, text="V", width=3, command=lambda: ae.config(
            show='' if ae.cget('show') == '*' else '*')).pack(side=tk.RIGHT)

        ttk.Label(f, text="Modelo IA:").pack(anchor=tk.W, pady=(10, 0))
        mf = ttk.Frame(f); mf.pack(fill=tk.X, pady=5)
        mv = tk.StringVar(value=self.config.get('groq_model', 'openai/gpt-oss-120b'))
        ttk.Combobox(mf, textvariable=mv, values=[
            'openai/gpt-oss-120b', 'llama-3.1-70b-versatile',
            'llama-3.1-8b-instant', 'gemma2-9b-it', 'mixtral-8x7b-32768'
        ], width=40).pack(side=tk.LEFT, fill=tk.X, expand=True)

        ttk.Label(f, text="Auto-save (segundos):").pack(anchor=tk.W, pady=(10, 0))
        sf = ttk.Frame(f); sf.pack(fill=tk.X, pady=5)
        sv = tk.IntVar(value=self.auto_save_interval)
        ttk.Spinbox(sf, from_=10, to=600, textvariable=sv, width=10).pack(side=tk.LEFT)
        asv = tk.BooleanVar(value=self.auto_save_enabled)
        ttk.Checkbutton(sf, text="Auto-save", variable=asv).pack(side=tk.LEFT, padx=10)

        ttk.Label(f, text="Limite de codigo para IA (chars):").pack(anchor=tk.W, pady=(10, 0))
        lf = ttk.Frame(f); lf.pack(fill=tk.X, pady=5)
        lv = tk.IntVar(value=self.config.get('ai_max_chars', AI_MAX_CODE_CHARS))
        ttk.Spinbox(lf, from_=2000, to=100000, increment=1000,
                    textvariable=lv, width=12).pack(side=tk.LEFT)
        ttk.Label(lf, text="  (recomendado: 16000)").pack(side=tk.LEFT)

        ttv = tk.BooleanVar(value=self.ai_auto_truncate)
        ttk.Checkbutton(f, text="Auto-truncar codigo grande antes de enviar a IA",
                        variable=ttv).pack(anchor=tk.W, pady=(5, 0))

        iv = tk.BooleanVar(value=self.icons_enabled)
        ttk.Checkbutton(f, text="Usar icones PNG", variable=iv).pack(anchor=tk.W, pady=(10, 0))
        acv = tk.BooleanVar(value=self.autocomplete_enabled)
        ttk.Checkbutton(f, text="Auto-complete", variable=acv).pack(anchor=tk.W, pady=(5, 0))
        litv = tk.BooleanVar(value=self.linter_enabled)
        ttk.Checkbutton(f, text="Linter Lua", variable=litv).pack(anchor=tk.W, pady=(5, 0))

        ttk.Label(f, text="Tema:").pack(anchor=tk.W, pady=(10, 0))
        tv = tk.StringVar(value=self.theme_name)
        tf2 = ttk.Frame(f); tf2.pack(fill=tk.X, pady=5)
        ttk.Radiobutton(tf2, text="Escuro", variable=tv, value='dark').pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(tf2, text="Claro", variable=tv, value='light').pack(side=tk.LEFT, padx=5)

        ttk.Label(f, text="Config: " + self.config.config_path,
                  font=("Arial", 8)).pack(anchor=tk.W, pady=5)

        ttk.Separator(f, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=15)
        bf = ttk.Frame(f); bf.pack(fill=tk.X, pady=10)
        ttk.Button(bf, text="SALVAR", command=lambda: self._save_settings(
            gv.get(), ov.get(), av.get(), mv.get(), sv.get(), asv.get(),
            iv.get(), acv.get(), litv.get(), ttv.get(), lv.get(),
            tv.get(), w)).pack(side=tk.LEFT, padx=5)
        ttk.Button(bf, text="Cancelar", command=w.destroy).pack(side=tk.RIGHT, padx=5)

    def _browse(self, var):
        d = filedialog.askdirectory()
        if d:
            var.set(d)

    def _save_settings(self, gp, op, ak, md, si, ase, use_ic, use_ac, use_lint,
                        use_trunc, max_chars, theme_sel, w):
        self.gmod_path = gp
        self.output_path = op
        self.api_key = ak
        self.ai_model = md
        self.auto_save_interval = int(si)
        self.auto_save_enabled = bool(ase)
        self.icons_enabled = bool(use_ic)
        self.autocomplete_enabled = bool(use_ac)
        self.linter_enabled = bool(use_lint)
        self.ai_auto_truncate = bool(use_trunc)
        global AI_MAX_CODE_CHARS
        AI_MAX_CODE_CHARS = int(max_chars)
        self.config['gmod_path'] = gp
        self.config['output_path'] = op
        self.config['groq_api_key'] = ak
        self.config['groq_model'] = md
        self.config['auto_save_interval'] = int(si)
        self.config['auto_save_enabled'] = bool(ase)
        self.config['use_icons'] = bool(use_ic)
        self.config['autocomplete_enabled'] = bool(use_ac)
        self.config['linter_enabled'] = bool(use_lint)
        self.config['ai_auto_truncate'] = bool(use_trunc)
        self.config['ai_max_chars'] = int(max_chars)
        self.ai.set_api_key(ak)
        self.ai.set_model(md)
        self.config.save()
        if theme_sel != self.theme_name:
            self.theme_name = theme_sel
            self.theme = THEMES[theme_sel]
            self.config['theme'] = theme_sel
            self.config.save()
            self.icons.clear()
            self._apply_ttk_style()
            self._apply_theme_to_widgets()
            if self.project_path:
                self.refresh_explorer()
        w.destroy()
        self.update_status("Configuracoes salvas")

    # =========================================
    # ADDON
    # =========================================

    def validate_structure(self):
        if not self.project_path:
            messagebox.showerror("Erro", "Abra um projeto!")
            return
        probs = []; warns = []
        if not os.path.exists(os.path.join(self.project_path, "lua")):
            probs.append("Falta 'lua/'")
        for d in ('materials', 'models', 'sound'):
            if not os.path.exists(os.path.join(self.project_path, d)):
                warns.append("Falta '" + d + "/'")
        has_icon = any(os.path.exists(os.path.join(self.project_path, "icon." + e))
                       for e in ('jpg', 'png'))
        if not has_icon:
            warns.append("Sem icon")
        msg = "Validacao\n\nProjeto: " + str(self.current_project) + "\n\n"
        if not probs and not warns:
            msg += "OK!"
        else:
            if probs:
                msg += "PROBLEMAS:\n" + "\n".join(probs) + "\n\n"
            if warns:
                msg += "AVISOS:\n" + "\n".join(warns)
        messagebox.showinfo("Validacao", msg)

    def compile_addon(self):
        if not self.current_project:
            messagebox.showerror("Erro", "Abra um projeto!")
            return
        self.save_all_tabs()
        gmad = os.path.join(self.gmod_path, "bin", "gmad.exe") if self.gmod_path else ""
        if not gmad or not os.path.exists(gmad):
            messagebox.showerror("Erro", "gmad.exe nao encontrado.")
            return
        os.makedirs(self.output_path, exist_ok=True)
        output = os.path.join(self.output_path, self.current_project + ".gma")
        if os.path.exists(output):
            try:
                os.remove(output)
            except Exception:
                pass
        pw = tk.Toplevel(self.root)
        pw.title("Compilando...")
        pw.geometry("400x150")
        pw.transient(self.root)
        pw.grab_set()
        ttk.Label(pw, text="Compilando...", font=("Arial", 12)).pack(pady=10)
        pb = ttk.Progressbar(pw, mode='indeterminate')
        pb.pack(pady=10, fill=tk.X, padx=20)
        pb.start()
        sl = ttk.Label(pw, text="Aguarde...", foreground="blue")
        sl.pack(pady=5)

        def worker():
            try:
                cmd = [gmad, "create", "-folder", self.project_path, "-output", output]
                p = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, text=True)
                out, err = p.communicate(timeout=120)
                self.root.after(0, pw.destroy)
                if p.returncode == 0 and os.path.exists(output):
                    sz = os.path.getsize(output) / 1024 / 1024
                    self.update_status("Compilado! (" + str(round(sz, 1)) + " MB)")
                    messagebox.showinfo("Sucesso", "Compilado:\n" + output)
                else:
                    messagebox.showerror("Erro", err or out or "Erro")
            except subprocess.TimeoutExpired:
                self.root.after(0, pw.destroy)
                messagebox.showerror("Erro", "Timeout")
            except Exception as e:
                self.root.after(0, pw.destroy)
                messagebox.showerror("Erro", str(e))

        threading.Thread(target=worker, daemon=True).start()

    def publish_addon(self):
        if not self.current_project:
            messagebox.showerror("Erro", "Abra um projeto!")
            return
        gma = os.path.join(self.output_path, self.current_project + ".gma")
        if not os.path.exists(gma):
            if messagebox.askyesno("Aviso", "Compilar primeiro?"):
                self.compile_addon()
                if not os.path.exists(gma):
                    return
        icon = None
        for e in ('jpg', 'png'):
            p = os.path.join(self.project_path, "icon." + e)
            if os.path.exists(p):
                icon = p; break
        if not icon and not messagebox.askyesno("Aviso", "Sem icone. Continuar?"):
            return
        gp = os.path.join(self.gmod_path, "bin", "gmpublish.exe") if self.gmod_path else ""
        if not gp or not os.path.exists(gp):
            messagebox.showerror("Erro", "gmpublish.exe nao encontrado.")
            return
        cmd = [gp, "create", "-addon", gma]
        if icon:
            cmd += ["-icon", icon]
        self.update_status("Publicando...")
        try:
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, text=True)
            out, err = p.communicate()
            if p.returncode == 0:
                m = re.search(r'id=(\d+)', out)
                wid = m.group(1) if m else "?"
                self.update_status("Publicado! ID: " + wid)
                messagebox.showinfo("Sucesso", "Publicado!\nID: " + wid)
            else:
                messagebox.showerror("Erro", err or out)
        except Exception as e:
            messagebox.showerror("Erro", str(e))

    def update_addon(self):
        if not self.current_project:
            messagebox.showerror("Erro", "Abra um projeto!")
            return
        wid = simpledialog.askstring("Workshop ID", "ID:")
        if not wid:
            return
        gma = os.path.join(self.output_path, self.current_project + ".gma")
        if not os.path.exists(gma):
            if messagebox.askyesno("Aviso", "Compilar primeiro?"):
                self.compile_addon()
                if not os.path.exists(gma):
                    return
        icon = None
        for e in ('jpg', 'png'):
            p = os.path.join(self.project_path, "icon." + e)
            if os.path.exists(p):
                icon = p; break
        gp = os.path.join(self.gmod_path, "bin", "gmpublish.exe") if self.gmod_path else ""
        if not gp or not os.path.exists(gp):
            messagebox.showerror("Erro", "gmpublish.exe nao encontrado.")
            return
        cmd = [gp, "update", "-id", wid, "-addon", gma]
        if icon:
            cmd += ["-icon", icon]
        self.update_status("Atualizando...")
        try:
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, text=True)
            out, err = p.communicate()
            if p.returncode == 0:
                self.update_status("Atualizado! ID: " + wid)
                messagebox.showinfo("Sucesso", "Atualizado!\nID: " + wid)
            else:
                messagebox.showerror("Erro", err or out)
        except Exception as e:
            messagebox.showerror("Erro", str(e))

    def open_addon_folder(self):
        if not self.project_path:
            messagebox.showerror("Erro", "Abra um projeto!")
            return
        os.startfile(self.project_path)

    def search_files(self):
        if not self.project_path:
            return
        txt = simpledialog.askstring("Buscar", "Texto:")
        if not txt:
            return
        results = []
        for root, _, files in os.walk(self.project_path):
            for f in files:
                if f.endswith(('.lua', '.txt', '.vmt')):
                    fp = os.path.join(root, f)
                    try:
                        with open(fp, 'r', encoding='utf-8') as fh:
                            if txt.lower() in fh.read().lower():
                                results.append(fp)
                    except Exception:
                        pass
        if results:
            messagebox.showinfo("Resultados",
                "Encontrado em " + str(len(results)) + ":\n\n" +
                "\n".join(results[:20]))
        else:
            messagebox.showinfo("Resultados", "Nao encontrado.")

    def show_stats(self):
        if not self.project_path:
            return
        stats = {}; total = 0
        for root, _, files in os.walk(self.project_path):
            for f in files:
                ext = os.path.splitext(f)[1].lower()
                stats[ext] = stats.get(ext, 0) + 1
                fp = os.path.join(root, f)
                if os.path.exists(fp):
                    total += os.path.getsize(fp)
        msg = "Estatisticas\n\n" + str(self.current_project) + "\n"
        msg += str(round(total / 1024 / 1024, 2)) + " MB\n"
        msg += str(sum(stats.values())) + " arquivos\n\n"
        for e, c in sorted(stats.items(), key=lambda x: x[1], reverse=True):
            msg += "  " + e + ": " + str(c) + "\n"
        messagebox.showinfo("Estatisticas", msg)

    def show_about(self):
        w = tk.Toplevel(self.root)
        w.title("Sobre")
        w.geometry("520x800")
        w.transient(self.root)
        w.grab_set()
        w.resizable(False, False)
        f = ttk.Frame(w, padding="15")
        f.pack(fill=tk.BOTH, expand=True)
        if PIL_AVAILABLE and os.path.exists(LOGO_PNG):
            try:
                img = Image.open(LOGO_PNG).convert("RGBA")
                if img.width > 120:
                    r = 120 / img.width
                    img = img.resize((120, int(img.height * r)), Image.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                lbl = ttk.Label(f, image=photo); lbl.image = photo
                lbl.pack(pady=(0, 10))
            except Exception:
                pass
        ttk.Label(f, text="GARRY'S MOD 13 ADDON EDITOR",
                  font=("Arial", 14, "bold")).pack(pady=(0, 2))
        ttk.Label(f, text="Versao: " + VERSION, font=("Arial", 10)).pack()
        ttk.Label(f, text="Autor: " + AUTHOR, font=("Arial", 10)).pack(pady=(0, 15))
        ttk.Separator(f, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=5)
        n_plugins = len(self.plugin_manager.get_enabled())
        n_total = len(self.plugin_manager.plugins)
        n_avail = len(self.plugin_manager.list_available())
        n_snips = len(self.snippet_manager.get_all())
        n_conv = len(self.ai_history.get_conversations())
        info = (
            "Novidades v5.2.1:\n"
            "- Truncamento inteligente de codigo grande\n"
            "- Contador de tokens no status bar\n"
            "- Aviso proativo antes de enviar pra IA\n"
            "- Config: limite de chars ajustavel\n\n"
            "Status:\n"
            "Tema: " + self.theme['name'] + "\n"
            "Plugins: " + str(n_plugins) + "/" + str(n_total) + " ativos\n"
            "Disponiveis: " + str(n_avail) + " no marketplace\n"
            "Snippets: " + str(n_snips) + "\n"
            "Conversas IA: " + str(n_conv) + "\n"
            "Pillow: " + ('OK' if PIL_AVAILABLE else 'nao') + "\n"
            "Groq: " + ('OK' if GROQ_AVAILABLE else 'nao') + "\n"
            "luaparser: " + ('OK' if LUAPARSER_AVAILABLE else 'nao') + "\n"
            "Git: " + ('OK' if self.git.available else 'nao') + "\n\n"
            "IA Limite: " + str(AI_MAX_CODE_CHARS) + " chars\n"
            "Auto-truncar: " + ("ON" if self.ai_auto_truncate else "OFF") + "\n\n"
            "Config: " + self.config.config_path + "\n"
            "Plugins: " + self.plugin_manager.plugins_dir + "\n"
            "Snippets: " + self.snippet_manager.snippets_dir + "\n"
            "Historico IA: " + self.ai_history.history_file
        )
        t = tk.Text(f, wrap=tk.WORD, font=("Consolas", 9), height=28,
                    bg=self.theme['bg'], fg=self.theme['fg'],
                    insertbackground=self.theme['insert'], relief=tk.FLAT)
        t.pack(fill=tk.BOTH, expand=True, pady=10)
        t.insert('1.0', info)
        t.config(state='disabled')
        ttk.Button(f, text="OK", command=w.destroy).pack(pady=5)

    def on_close(self):
        dirty = []
        for fp, (_, tw, _) in self.open_tabs.items():
            try:
                cur = tw.get('1.0', tk.END).rstrip('\n')
                if os.path.exists(fp):
                    with open(fp, 'r', encoding='utf-8') as f:
                        sv = f.read().rstrip('\n')
                    if cur != sv:
                        dirty.append(fp)
            except Exception:
                pass
        if dirty:
            resp = messagebox.askyesnocancel("Sair",
                str(len(dirty)) + " arquivo(s) nao salvos. Salvar?")
            if resp is None:
                return
            if resp:
                self.save_all_tabs()
        self.save_config()
        self.root.destroy()


# ==============================================
# MAIN
# ==============================================

def main():
    print("GMod 13 Addon Editor v" + VERSION)
    print("   Pillow: " + str(PIL_AVAILABLE))
    print("   Groq: " + str(GROQ_AVAILABLE))
    print("   luaparser: " + str(LUAPARSER_AVAILABLE))
    print("   IA limite de codigo: " + str(AI_MAX_CODE_CHARS) + " chars")

# Jumpscare SFX aqui.

    if DND_AVAILABLE:
        try:
            root = TkinterDnD.Tk()
        except Exception as e:
            print("DND falhou: " + str(e))
            root = tk.Tk()
    else:
        root = tk.Tk()

    root.withdraw()
    splash = SplashScreen(root, SPLASH_FILE, SPLASH_DURATION_MS)
    app = GMODEditor(root)

    def _show_main():
        if splash.win and not splash.closed:
            root.after(200, _show_main)
            return
        try:
            root.deiconify()
            root.lift()
            root.focus_force()
        except Exception:
            root.deiconify()

# saiu ;(
    root.after(300, _show_main)
    root.mainloop()
    print("Ate logo!")


if __name__ == "__main__":
    main()