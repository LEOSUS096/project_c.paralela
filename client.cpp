// client.cpp FINAL - Version sin modo BOTH
// Compilar: g++ client.cpp -o client -fopenmp -O2

#include <bits/stdc++.h>
#include <omp.h>
#include <sys/socket.h>
#include <arpa/inet.h>
#include <unistd.h>

using namespace std;
using clk = chrono::high_resolution_clock;

// ------------------------------------------------------------
// Simulación de una trayectoria Monte Carlo
// ------------------------------------------------------------
double simulate_one_path(double S0, double mu, double sigma, int steps, std::mt19937 &gen) {
    std::normal_distribution<> dist(0.0, 1.0);
    double S = S0;
    double dt = 1.0 / steps;

    for (int t = 0; t < steps; ++t) {
        double Z = dist(gen);
        S *= exp((mu - 0.5 * sigma * sigma) * dt + sigma * sqrt(dt) * Z);
    }
    return S;
}

int main(int argc, char** argv) {

    if (argc < 9) {
        cerr << "Usage: " << argv[0] 
             << " <server_ip> <port> <TICKER> <years> <simulations> <steps> <mode> <threads>\n";
        cerr << "mode: seq | omp\n";
        return 1;
    }

    string server_ip = argv[1];
    int port         = stoi(argv[2]);
    string ticker    = argv[3];
    int years        = stoi(argv[4]);
    long long simulations = stoll(argv[5]);
    int steps        = stoi(argv[6]);
    string mode      = argv[7];
    int threads      = stoi(argv[8]);

    // ------------------------------------------------------------
    // 1. Solicitar parámetros al servidor
    // ------------------------------------------------------------
    int sock = socket(AF_INET, SOCK_STREAM, 0);
    if (sock < 0) { perror("socket"); return 2; }

    struct sockaddr_in serv;
    serv.sin_family = AF_INET;
    serv.sin_port   = htons(port);

    if (inet_pton(AF_INET, server_ip.c_str(), &serv.sin_addr) <= 0) {
        perror("inet_pton");
        return 3;
    }
    if (connect(sock, (struct sockaddr*)&serv, sizeof(serv)) != 0) {
        perror("connect");
        return 4;
    }

    string req = "GET " + ticker + " " + to_string(years) + "\n";
    send(sock, req.c_str(), req.size(), 0);

    char buf[256];
    ssize_t r = recv(sock, buf, sizeof(buf)-1, 0);
    if (r <= 0) {
        cerr << "No response from server\n";
        close(sock);
        return 5;
    }
    buf[r] = 0;
    close(sock);

    // Server error?
    if (string(buf).rfind("ERROR", 0) == 0) {
        cerr << "Server error: " << buf << "\n";
        return 6;
    }

    // parse mu, sigma, S0
    double mu, sigma, S0;
    if (sscanf(buf, "%lf %lf %lf", &mu, &sigma, &S0) != 3) {
        cerr << "Bad server reply: " << buf << "\n";
        return 7;
    }

    cout << fixed << setprecision(8);
    cout << "Params from server: ticker=" << ticker 
         << " S0=" << S0 << " mu=" << mu << " sigma=" << sigma << "\n";

    // ------------------------------------------------------------
    // Archivos de salida
    // ------------------------------------------------------------
    string results_csv = "results.csv";
    string traj_csv    = "trajectories.csv";

    // ------------------------------------------------------------
    // Función lambda para correr Monte Carlo secuencial o paralelo
    // ------------------------------------------------------------
    auto run_montecarlo = [&](bool parallel, int threads_use, double &avg_final, double &time_sec) 
    {
        auto t0 = clk::now();
        long long N = simulations;

        vector<double> finals(N);

        if (!parallel) {
            // SECUENCIAL
            std::mt19937 gen(12345);
            for (long long i = 0; i < N; ++i)
                finals[i] = simulate_one_path(S0, mu, sigma, steps, gen);

        } else {
            // PARALLEL OMP
            omp_set_num_threads(threads_use);

            #pragma omp parallel
            {
                int tid = omp_get_thread_num();
                std::mt19937 gen(
                    (unsigned)chrono::system_clock::now().time_since_epoch().count() + tid * 7919
                );

                #pragma omp for schedule(dynamic)
                for (long long i = 0; i < N; ++i)
                    finals[i] = simulate_one_path(S0, mu, sigma, steps, gen);
            }
        }

        auto t1 = clk::now();
        time_sec = chrono::duration<double>(t1 - t0).count();

        long double sum = 0;
        for (double v : finals) sum += v;
        avg_final = sum / N;

        // --------------------------------------------------------
        // Guardar 20 trayectorias de ejemplo para las gráficas web
        // --------------------------------------------------------
        int M = min<long long>(20LL, simulations);

        bool exists = std::ifstream(traj_csv).good();
        ofstream ftraj(traj_csv, ios::app);

        if (!exists)
            ftraj << "ticker,sim_id,day,price\n";

        for (int s = 0; s < M; ++s) {
            std::mt19937 gen(1000 + s);
            double S = S0;

            // día 0
            ftraj << ticker << "," << s << ",0," << S << "\n";

            for (int d = 1; d <= steps; ++d) {
                std::normal_distribution<> dist(0.0,1.0);
                double Z = dist(gen);

                S *= exp((mu - 0.5 * sigma * sigma) * (1.0/steps)
                       + sigma * sqrt(1.0/steps) * Z);

                ftraj << ticker << "," << s << "," << d << "," << S << "\n";
            }
        }

        ftraj.close();
    };

    // ------------------------------------------------------------
    // Ejecutar SOLO el modo pedido: seq o omp
    // ------------------------------------------------------------
    double avg_seq = 0.0, t_seq = 0.0;
    double avg_omp = 0.0, t_omp = 0.0;

    if (mode == "seq") {
        cout << "[RUN] Sequential...\n";
        run_montecarlo(false, 1, avg_seq, t_seq);
        cout << "[DONE] avg_final=" << avg_seq << " time=" << t_seq << "s\n";
    }
    else if (mode == "omp") {
        cout << "[RUN] OpenMP (" << threads << " threads)...\n";
        run_montecarlo(true, threads, avg_omp, t_omp);
        cout << "[DONE] avg_final=" << avg_omp << " time=" << t_omp << "s\n";
    }
    else {
        cerr << "ERROR: mode must be seq or omp\n";
        return 10;
    }

    // ------------------------------------------------------------
    // Guardar RESULTADOS SIMPLIFICADOS
    // ------------------------------------------------------------
    bool exists = std::ifstream(results_csv).good();
    ofstream fres(results_csv, ios::app);

    if (!exists)
        fres << "ticker,simulations,steps,threads,mode,avg_final,time_sec\n";

    if (mode == "seq") {
        fres << ticker << "," << simulations << "," << steps << ",1,"
             << "seq," << avg_seq << "," << t_seq << "\n";
    }
    else if (mode == "omp") {
        fres << ticker << "," << simulations << "," << steps << "," << threads << ","
             << "omp," << avg_omp << "," << t_omp << "\n";
    }

    fres.close();

    cout << "[Saved] results to " << results_csv << "\n";
    cout << "[Saved] sample trajectories to " << traj_csv << "\n";

    return 0;
}
