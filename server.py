import socket
import threading
import yfinance as yf
import numpy as np
import pandas as pd

HOST = "0.0.0.0"
PORT = 9000

def calc_params(ticker, years):
    df = yf.download(ticker, period=f"{years}y", progress=False)
    if df.empty:
        raise RuntimeError("No data for ticker " + ticker)

    df['log_return'] = np.log(df['Close'] / df['Close'].shift(1))
    df.dropna(inplace=True)

    mu = df['log_return'].mean()
    sigma = df['log_return'].std()
    S0 = df['Close'].iloc[-1]

    return float(mu), float(sigma), float(S0)

def handle_client(conn, addr):
    with conn:
        try:
            req = conn.recv(256).decode().strip()
            parts = req.split()

            # Validación comando
            if len(parts) < 2 or parts[0].upper() != "GET":
                conn.sendall(b"ERROR bad request\n")
                return

            ticker = parts[1].upper()
            years = int(parts[2]) if len(parts) >= 3 else 5

            mu, sigma, S0 = calc_params(ticker, years)

            line = f"{mu} {sigma} {S0}\n"
            conn.sendall(line.encode())

            print(f"[{addr}] served {ticker} mu={mu:.6g} sigma={sigma:.6g} S0={S0:.4f}")

        except Exception as e:
            msg = "ERROR " + str(e) + "\n"
            try:
                conn.sendall(msg.encode())
            except:
                pass
            print(f"[{addr}] error: {e}")

def main():
    print(f"[SERVER] Starting on port {PORT}")

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    # 🔥 FIX: permite reusar el puerto inmediatamente
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    sock.bind((HOST, PORT))
    sock.listen(5)

    try:
        while True:
            conn, addr = sock.accept()
            thread = threading.Thread(target=handle_client, args=(conn, addr))
            thread.daemon = True
            thread.start()

    finally:
        sock.close()

if __name__ == "__main__":
    main()
