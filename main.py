from services.updater import check_pending_update
from ui.app import JanelaCrosara

if __name__ == "__main__":
    # Aplica update pendente (baixado em sessao anterior) ANTES de abrir UI.
    # Se aplicou, o processo morre aqui e o updater.bat reabre depois.
    check_pending_update()
    JanelaCrosara()
