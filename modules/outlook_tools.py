class OutlookTools:
    """Lectura y borradores de correo a través de Outlook de escritorio (Windows, vía COM)."""

    def __init__(self):
        self.outlook = None

    def _conectar(self):
        try:
            import win32com.client
            self.outlook = win32com.client.Dispatch("Outlook.Application")
            return True
        except Exception:
            self.outlook = None
            return False

    def leer_correos(self, n=5):
        if not self._conectar():
            return "No pude conectar con Outlook. ¿Está instalado y configurado?"
        try:
            namespace = self.outlook.GetNamespace("MAPI")
            inbox = namespace.GetDefaultFolder(6)  # 6 = Bandeja de entrada
            items = inbox.Items
            items.Sort("[ReceivedTime]", True)
            res = []
            limite = min(int(n), items.Count)
            for i in range(limite):
                m = items.Item(i + 1)
                try:
                    res.append(f"De {m.SenderName}: {m.Subject}")
                except Exception:
                    continue
            if not res:
                return "No hay correos recientes en la bandeja de entrada."
            return "Tus últimos correos son: " + " | ".join(res) + "."
        except Exception as e:
            return f"No pude leer los correos: {e}"

    def crear_borrador(self, destinatario, asunto, cuerpo):
        if not self._conectar():
            return "No pude conectar con Outlook. ¿Está instalado y configurado?"
        try:
            mail = self.outlook.CreateItem(0)  # 0 = MailItem
            mail.To = destinatario
            mail.Subject = asunto
            mail.Body = cuerpo
            mail.Save()  # queda en la carpeta Borradores
            return f"Borrador creado para {destinatario} con asunto '{asunto}'."
        except Exception as e:
            return f"No pude crear el borrador: {e}"
