# GMOD 13 EDITOR (GME)

**Um editor de addons para Garry's Mod 13 (Windows)**

![GitHub release (latest by date)](https://img.shields.io/github/v/release/lixbot85-dot/gmod13-editor-br)
![GitHub downloads](https://img.shields.io/github/downloads/lixbot85-dot/gmod13-editor-br/total)
![GitHub license](https://img.shields.io/github/license/lixbot85-dot/gmod13-editor-br)

---

## O que é?

O **GMOD 13 Editor** é uma ferramenta completa e intuitiva para criar, editar e publicar addons para o **Garry's Mod 13**. 
Com uma interface estilo VS Code, você pode criar SWEPs, entidades, importar assets e compilar seus addons diretamente para o Workshop.

---

## Funcionalidades

### Editor de Código
- Syntax highlighting para Lua
- Tabs estilo VS Code (Ctrl+W para fechar)
- Auto-indent e busca/substituição
- Números de linha

### Explorador de Arquivos
- Navegação completa pelo projeto
- Criar, renomear, deletar arquivos/pastas
- Importar arquivos via Drag & Drop
- Exportar assets para .zip

### Templates Prontos
| Tipo | Base | Arquivo gerado |
|------|------|----------------|
| SWEP | 308 Base | `weapon_nome.lua` |
| SWEP | Standalone | `weapon_nome.lua` |
| ENTITY | VJ Base | `shared.lua` |
| ENTITY | DRG Base | `shared.lua` |
| ENTITY | Standalone | `shared.lua` |

### AI Assistant (Groq)
- **Corrigir Bug**: Encontra e corrige erros no seu código
- **Sugestão**: Dá ideias para melhorar o código
- **Explicar Código**: Explica o que o código faz em português
- Modelos: `openai/gpt-oss-120b` (recomendado), `llama-3.1-70b-versatile`, `gemma2-9b-it`

### Addon Tools
- Compilar addon (`.gma`) via `gmad.exe`
- Publicar no Workshop (primeira vez)
- Atualizar addon no Workshop
- Exportar assets para `.zip`

---

## Download

| Versão | Download | Descrição |
|--------|----------|-----------|
| **v4.9** | [ Baixar](https://github.com/lixbot85-dot/gmod13-editor-br/releases/latest) | **Recomendada** - Com AI Assistant |
| **v4.3** | [ Baixar](https://github.com/lixbot85-dot/gmod13-editor-br/releases/tag/v4.3) | Versão anterior (sem AI Assistant) |

> ** Requisitos:** Windows 7 ou superior. Não precisa de Python instalado.

---

## Como Usar

### Baixe e execute
Baixe o arquivo `GMOD_Editor.exe` da página de releases e execute.

### Configure
- **Arquivo > Configurações**
- Defina a pasta do Garry's Mod (ex: `C:/Program Files (x86)/Steam/steamapps/common/GarrysMod`)
- Defina a pasta de output (onde os addons compilados serão salvos)
- (Opcional) Configure a API Key do Groq para usar o AI Assistant

### Crie um projeto
- **Arquivo > Novo Projeto** ou `Ctrl+N`
- Dê um nome para seu projeto

### Comece a criar
- Clique com o botão direito no explorador
- Escolha **Criar > SWEP/ENTITY** e selecione o template desejado
- Edite o código gerado
- Pressione `F5` para compilar

---

## Atalhos

| Tecla | Ação |
|-------|------|
| `Ctrl+N` | Novo Projeto |
| `Ctrl+O` | Abrir Projeto |
| `Ctrl+S` | Salvar arquivo atual |
| `Ctrl+W` | Fechar tab atual |
| `Ctrl+Q` | Sair |
| `F5` | Compilar Addon |
| `F6` | Publicar Addon |
| `F7` | Atualizar Addon |

---

## Suporte a Arquivos

| Tipo | Extensões |
|------|-----------|
| **Lua** | `.lua`, `.txt` |
| **Imagens** | `.png`, `.jpg`, `.jpeg`, `.tga` |
| **Materiais** | `.vmt`, `.vtf` |
| **Modelos** | `.mdl`, `.vvd`, `.vtx`, `.phy`, `.smd`, `.qc` |
| **Sons** | `.wav`, `.mp3`, `.ogg`, `.flac` |
| **Partículas** | `.pcf` |
| **Outros** | `.zip`, `.json` |

---

## Configuração do AI Assistant

1. Acesse [console.groq.com](https://console.groq.com) e crie uma conta (gratuita)
2. Gere uma API Key
3. No editor, vá em **Arquivo > Configurações**
4. Cole a API Key no campo **Groq API Key**
5. Selecione o modelo desejado
6. Clique em **Salvar**

---

## FAQ

**O editor é gratuito?**  
Sim! Totalmente gratuito.

**Precisa de Python para rodar?**  
Não, o executável já inclui tudo que precisa.

**O AI Assistant é gratuito?**  
Sim! A Groq oferece uma API gratuita com limite generoso.

**Posso usar sem o 308 Base?**  
Sim, os templates Standalone não exigem nenhuma base externa.

---

## Licença

Este projeto está sob a licença **Apache License 2.0** - veja o arquivo [LICENSE](LICENSE) para mais detalhes.

---

## Agradecimentos

- Comunidade do Garry's Mod
- [Groq](https://groq.com) pela API gratuita
- Todos que testaram e contribuíram

---

## Links

- [Steam Workshop do Addon](https://steamcommunity.com/sharedfiles/filedetails/?id=3746919258)
- [Groq Console](https://console.groq.com)
- [Garry's Mod](https://garrysmod.com/)

---

**Feito com ❤️ para a comunidade GMod** 🇧🇷
