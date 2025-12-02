import os
import subprocess
from flask import Flask, render_template, request, send_file, send_from_directory, Response, redirect, url_for
import io
import pandas as pd
import matplotlib
matplotlib.use('Agg')   # backend para servidores (sin GUI)
import matplotlib.pyplot as plt
from datetime import datetime

app = Flask(__name__)

# === RESOLVER RUTAS AUTOMÁTICAMENTE ===
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CLIENT_BIN = os.path.join(BASE_DIR, "client")  # ruta correcta al ejecutable

SERVER_IP = "192.168.56.1"   # <-- Cambia por la IP real de tu servidor Python
PORT = "9000"

# Guarda el último ticker ejecutado para la vista (opcional, simple)
LAST_RUN_INFO = os.path.join(BASE_DIR, "last_run.info")

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/run", methods=["POST"])
def run_simulation():
    ticker = request.form["ticker"].upper()
    years = request.form["years"]
    sims = request.form["simulations"]
    steps = request.form["steps"]
    mode = request.form["mode"]
    threads = request.form["threads"]

    # Ejecutar cliente C++
    cmd = [
        CLIENT_BIN,
        SERVER_IP,
        PORT,
        ticker,
        years,
        sims,
        steps,
        mode,
        threads
    ]

    print("Running:", " ".join(cmd))

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=BASE_DIR,
            timeout=None
        )
    except Exception as e:
        return render_template("result.html", output=f"ERROR: No se puede ejecutar el cliente.\n{e}", plot_url=None)

    output = result.stdout + "\n" + result.stderr

    # guarda información simple para /plot (último ticker usado)
    try:
        with open(LAST_RUN_INFO, "w") as f:
            f.write(f"{ticker}\n")
            f.write(f"{datetime.now().isoformat()}\n")
    except:
        pass

    # URL para mostrar la imagen (evita cache con timestamp)
    plot_url = url_for('plot_png', ticker=ticker, t=int(datetime.now().timestamp()))
    return render_template("result.html", output=output, plot_url=plot_url)

@app.route("/plot.png")
def plot_png():
    """
    Genera y devuelve PNG en memoria a partir de trajectories.csv.
    Parámetros opcionales via querystring:
      - ticker : filtrar por ticker (ej: AAPL)
      - max_sim : máximo número de trayectorias a dibujar (default 20)
    """
    ticker = request.args.get("ticker", None)
    max_sim = int(request.args.get("max_sim", 20))
    traj_path = os.path.join(BASE_DIR, "trajectories.csv")

    if not os.path.exists(traj_path):
        # devolver imagen simple con mensaje
        fig, ax = plt.subplots(figsize=(6,3))
        ax.text(0.5, 0.5, "No trajectories.csv found", ha='center', va='center')
        ax.axis('off')
        buf = io.BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight')
        plt.close(fig)
        buf.seek(0)
        return Response(buf.getvalue(), mimetype='image/png')

    # leer CSV
    try:
        df = pd.read_csv(traj_path)
    except Exception as e:
        fig, ax = plt.subplots(figsize=(6,3))
        ax.text(0.5, 0.5, f"Error reading CSV:\n{e}", ha='center', va='center', wrap=True)
        ax.axis('off')
        buf = io.BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight')
        plt.close(fig)
        buf.seek(0)
        return Response(buf.getvalue(), mimetype='image/png')

    if ticker:
        df = df[df['ticker'] == ticker]

    if df.empty:
        fig, ax = plt.subplots(figsize=(6,3))
        ax.text(0.5, 0.5, "No data for selected ticker", ha='center', va='center')
        ax.axis('off')
        buf = io.BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight')
        plt.close(fig)
        buf.seek(0)
        return Response(buf.getvalue(), mimetype='image/png')

    # plot up to max_sim distinct sim_id
    # asumimos columnas: ticker, sim_id, day, price
    sim_ids = sorted(df['sim_id'].unique())[:max_sim]

    fig, ax = plt.subplots(figsize=(10,6))
    for sid in sim_ids:
        g = df[df['sim_id'] == sid]
        ax.plot(g['day'], g['price'], alpha=0.7, linewidth=1)

    ax.set_title(f"Muestra de trayectorias Monte Carlo ({ticker if ticker else 'all'})")
    ax.set_xlabel("Dia")
    ax.set_ylabel("Precio")
    ax.grid(True)

    # convertir a PNG en memoria
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight')
    plt.close(fig)
    buf.seek(0)
    return Response(buf.getvalue(), mimetype='image/png')

@app.route("/download_results")
def download_results():
    path = os.path.join(BASE_DIR, "results.csv")
    if os.path.exists(path):
        return send_file(path, as_attachment=True)
    return "results.csv no existe."

@app.route("/download_trajectories")
def download_trajectories():
    path = os.path.join(BASE_DIR, "trajectories.csv")
    if os.path.exists(path):
        return send_file(path, as_attachment=True)
    return "trajectories.csv no existe."

if __name__ == "__main__":
    app.run(debug=True)