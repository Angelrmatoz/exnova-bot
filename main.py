from bot.broker.exnova import ExnovaAdapter
from bot.config import exnova_credentials
from bot.menu import choose_assets, choose_market


def main():
    market = choose_market()
    creds = exnova_credentials()
    broker = ExnovaAdapter(creds["email"], creds["password"], creds["account_type"], market)

    print("Conectando a Exnova...")
    ok, reason = broker.connect()
    if not ok:
        print(f"Error de conexión: {reason}. Revisa credenciales o activa 2FA.")
        return
    print("Conectado.\n")

    assets = choose_assets(broker)
    if not assets:
        return


if __name__ == "__main__":
    main()