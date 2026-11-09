package io.insightradar.v002;

import java.io.IOException;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.TimeUnit;

/** A disposable native cluster: never reads DB_URL or any application database. */
final class LocalPostgres implements AutoCloseable {
    private final Path bin;
    private final Path root;
    private final Path data;
    private final Path output;
    private int port;

    LocalPostgres() throws IOException {
        List<Path> candidates = new ArrayList<>();
        String configured = System.getenv("PG_BIN");
        if (configured != null && !configured.isBlank()) candidates.add(Path.of(configured));
        else {
            for (String path : List.of("/opt/homebrew/opt/postgresql@17/bin", "/usr/local/opt/postgresql@17/bin", "/usr/lib/postgresql/17/bin")) candidates.add(Path.of(path));
            for (String path : System.getenv().getOrDefault("PATH", "").split(java.io.File.pathSeparator)) candidates.add(Path.of(path));
        }
        bin = candidates.stream().filter(p -> Files.isExecutable(p.resolve("pg_ctl"))).findFirst()
            .orElseThrow(() -> new IOException("Install PostgreSQL 17 or set PG_BIN; database tests are required, not skipped"));
        root = Files.createTempDirectory("ir-v002-pg-");
        data = root.resolve("cluster");
        output = root.resolve("commands.log");
    }

    void start() throws Exception {
        run("postgres", "--version");
        if (!Files.readString(output).matches("(?s).*PostgreSQL\\)? 17\\..*")) throw new IOException("PostgreSQL 17 required");
        run("initdb", "-D", data.toString(), "-U", "test_user", "--encoding=UTF8", "--locale=C", "--auth=trust");
        try (ServerSocket socket = new ServerSocket(0, 1, InetAddress.getByName("127.0.0.1"))) { port = socket.getLocalPort(); }
        // No Unix socket: macOS temporary paths can exceed Unix socket path limits.
        run("pg_ctl", "-D", data.toString(), "-l", root.resolve("postgres.log").toString(),
            "-o", "-h 127.0.0.1 -p " + port + " -k ''", "-w", "-t", "20", "start");
        run("createdb", "-h", "127.0.0.1", "-p", String.valueOf(port), "-U", "test_user", "integration_test");
    }

    void restart() throws Exception {
        run("pg_ctl", "-D", data.toString(), "-m", "fast", "-w", "-t", "20", "restart");
    }

    String jdbcUrl() { return "jdbc:postgresql://127.0.0.1:" + port + "/integration_test"; }

    private void run(String command, String... args) throws Exception {
        List<String> argv = new ArrayList<>(List.of(bin.resolve(command).toString()));
        argv.addAll(List.of(args));
        ProcessBuilder builder = new ProcessBuilder(argv).redirectErrorStream(true).redirectOutput(ProcessBuilder.Redirect.appendTo(output.toFile()));
        // Test identity, host, port and auth must not inherit a developer's PG service config.
        builder.environment().keySet().removeIf(key -> key.startsWith("PG"));
        Process process = builder.start();
        if (!process.waitFor(30, TimeUnit.SECONDS)) { process.destroyForcibly(); throw new IOException(command + " timed out; logs: " + root); }
        if (process.exitValue() != 0) throw new IOException(command + " failed: " + Files.readString(output));
    }

    @Override public void close() throws Exception {
        if (Files.exists(data.resolve("postmaster.pid"))) run("pg_ctl", "-D", data.toString(), "-m", "fast", "-w", "-t", "20", "stop");
        if (Files.exists(root)) {
            try (var paths = Files.walk(root)) {
                for (Path path : paths.sorted(Comparator.reverseOrder()).toList()) Files.delete(path);
            }
        }
    }
}
