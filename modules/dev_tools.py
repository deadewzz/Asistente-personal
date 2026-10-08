import subprocess

from modules import rutas


class DevTools:
    """Herramientas para desarrollo: contexto de Git (para commits), comandos de
    terminal seguros y control de contenedores."""

    # Comandos seguros mapeados por intención de voz (ampliable en config)
    COMANDOS_SEGUROS = {
        "tests": "pytest",
        "test": "pytest",
        "test unitario": "pytest",
        "docker up": "docker compose up -d",
        "docker down": "docker compose down",
        "encender docker": "docker compose up -d",
        "apagar docker": "docker compose down",
    }

    def __init__(self, config_path=rutas.CONFIG_USUARIO):
        self.config_path = config_path

    def obtener_contexto_git(self):
        """Devuelve status + diff para que el cerebro redacte un mensaje de commit."""
        status = self._run(["git", "status", "--short"])
        diff = self._run(["git", "diff", "--stat"])
        if not status and not diff:
            return "No se detectó un repositorio Git en esta carpeta o no hay cambios pendientes."
        return f"Cambios en Git:\n{status}\n\nResumen del diff:\n{diff}"

    def ejecutar_comando(self, clave):
        clave = clave.lower().strip()
        comando = self.COMANDOS_SEGUROS.get(clave)
        if comando is None:
            return f"No tengo un comando seguro mapeado para '{clave}'. Añádelo en config."
        return self._run(comando, shell=True)

    def _run(self, cmd, shell=False, timeout=90):
        try:
            if shell:
                p = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                                   timeout=timeout, encoding="utf-8", errors="replace")
            else:
                p = subprocess.run(cmd, capture_output=True, text=True,
                                   timeout=timeout, encoding="utf-8", errors="replace")
            salida = (p.stdout or "").strip()
            error = (p.stderr or "").strip()
            resultado = salida or error or "Comando ejecutado sin salida."
            return resultado[-3000:]
        except subprocess.TimeoutExpired:
            return "El comando tardó demasiado y fue cancelado."
        except Exception as e:
            return f"Error al ejecutar el comando: {e}"
