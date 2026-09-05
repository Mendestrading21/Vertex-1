"""
test_connection.py — Preuve de connexion IBKR en DONNEES DE MARCHE seulement.
Sonde les ports API IBKR, ouvre une session marche (poignee de main, aucune
lecture de compte, positions, ordres ni executions), affiche l'heure du
courtier et 5 bougies AAPL.

Frontiere Vertex : ce script ne lit JAMAIS le compte. Le resume de compte et
la liste des lignes detenues qu'il affichait ont ete retires (IBKR = source
de marche uniquement ; le portefeuille est declare par l'utilisateur).

PREREQUIS (cote TWS) :
  1. TWS logge.
  2. API activee : Global Configuration > API > Settings
       - cocher "Enable ActiveX and Socket Clients"
       - Socket port = 7496 (TWS reel) [paper = 7497]
       - 127.0.0.1 en "Trusted IPs" (ou "localhost only")
       - "Read-Only API" COCHE  -> verrou anti-ordre.
  3. A la 1re connexion, TWS demande "Accept incoming connection" -> Accept.
"""
from ib_reader import IBKRReader, LIVE_PORT


def main() -> None:
    reader = IBKRReader(port=LIVE_PORT)  # 7496 = REEL en 1er, puis fallback auto
    try:
        reader.connect_auto()
    except Exception as e:
        print(f"[ERREUR] {e}")
        print("  -> TWS lance + API activee + 127.0.0.1 en IP de confiance ?")
        return

    print("\n-- Session marche seulement --")
    print(f"  heure du courtier : {reader.ib.reqCurrentTime()}")
    from vertex.data_sources import ibkr_session
    print(f"  session verrouillee (aucune lecture de compte possible) : "
          f"{ibkr_session.est_verrouillee(reader.ib)}")

    print("\n-- Bougies AAPL (daily, 5 dernieres) --")
    bars = reader.historical_bars("AAPL", duration="1 M", bar_size="1 day")
    if bars is not None and not bars.empty:
        cols = [c for c in ("date", "open", "high", "low", "close", "volume") if c in bars.columns]
        print(bars.tail()[cols].to_string(index=False))
    else:
        print("  (pas de donnees — verifie les souscriptions market data IBKR)")

    reader.disconnect()


if __name__ == "__main__":
    main()
