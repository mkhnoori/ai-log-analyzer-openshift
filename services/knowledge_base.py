import uuid
from loguru import logger
from services.embedder import Embedder
from services.vector_store import VectorStore

SEED_INCIDENTS = [
    (
        "npm ERR! code ERESOLVE\nnpm ERR! ERESOLVE unable to resolve dependency tree\nnpm ERR! Found: react@18.2.0",
        "npm peer dependency conflict — incompatible versions between packages in package.json",
        "Add --legacy-peer-deps to npm install, or pin the conflicting dependency versions",
    ),
    (
        "Error: EACCES: permission denied, open '/root/.npm/_cacache/tmp'",
        "npm cache permission error — process running as wrong user or cache dir has wrong ownership",
        "Run: npm config set cache /tmp/.npm-cache-$USER  or fix ownership with chown",
    ),
    (
        "fatal: unable to access 'https://github.com/': Could not resolve host: github.com",
        "DNS resolution failure — CI runner cannot reach GitHub, likely network/DNS misconfiguration",
        "Check runner network config, add 8.8.8.8 as DNS server, or whitelist github.com",
    ),
    (
        "java.lang.OutOfMemoryError: Java heap space\n\tat java.base/java.util.Arrays.copyOf",
        "JVM heap exhausted during Maven/Gradle build — default heap too small for this project",
        "Set MAVEN_OPTS=-Xmx2g or add -Xmx2g to JAVA_TOOL_OPTIONS in CI environment",
    ),
    (
        "Error response from daemon: pull access denied for myregistry.io/app:latest",
        "Docker registry authentication failure — CI credentials missing or expired",
        "Re-run docker login in CI, update DOCKER_PASSWORD secret, check token expiry",
    ),
    (
        "FAILED tests/test_api.py::test_login - AssertionError: assert 401 == 200",
        "Test failure — auth endpoint returning 401, JWT_SECRET env var missing in test environment",
        "Add JWT_SECRET (or equivalent) to the test environment variables in CI config",
    ),
    (
        "ERROR: could not connect to server: Connection refused — Is the server running on host \"db\" port 5432?",
        "PostgreSQL not ready when app started — missing health check on database service",
        "Add depends_on with condition: service_healthy in docker-compose, or use wait-for-it.sh",
    ),
    (
        "error: failed to push some refs to 'origin' — Updates were rejected because the remote contains work",
        "Git push rejected — concurrent pipeline runs created divergent history on the same branch",
        "Add git pull --rebase before push, or use a deploy key with force-push, or serialize jobs",
    ),
    (
        "ERROR: Could not install packages due to an OSError: [Errno 28] No space left on device",
        "Disk full on CI runner — large package exhausted available disk space",
        "Run docker system prune -af before build, increase runner disk, or cache pip packages",
    ),
    (
        "SyntaxError: Unexpected token '<' at JSON.parse  webpack.config.js:42",
        "webpack config JSON parse error — endpoint returned an HTML error page instead of JSON",
        "Fix the config endpoint URL, or correct the JSON syntax in webpack.config.js",
    ),
    (
        "Waiting for database...\nConnection refused (port 5432)\nConnection refused (port 5432)\nExiting after 30 retries",
        "Database startup timeout — app container started before Postgres finished initializing",
        "Add a proper health check with pg_isready to the database service, increase retry count",
    ),
    (
        "fatal error: Python.h: No such file or directory\ncompilation terminated.\nerror: command gcc failed",
        "Missing Python development headers — gcc cannot compile a C extension (e.g. psycopg2, numpy)",
        "Install python3-dev (Debian) or python3-devel (RPM) in the CI Docker image",
    ),
]


async def seed_knowledge_base(embedder: Embedder, store: VectorStore):
    if store.col.count() >= len(SEED_INCIDENTS):
        logger.info(f"Knowledge base already seeded ({store.col.count()} incidents)")
        return
    logger.info("Seeding knowledge base with curated incidents...")
    for i, (snippet, cause, fix) in enumerate(SEED_INCIDENTS):
        emb = await embedder.embed(snippet)
        store.add_incident(
            incident_id=uuid.uuid4().hex[:8],
            embedding=emb,
            log_snippet=snippet,
            root_cause=cause,
            fix_applied=fix,
            confidence=1.0,
        )
        logger.info(f"  Seeded {i + 1}/{len(SEED_INCIDENTS)}")
    logger.success(f"Knowledge base ready — {len(SEED_INCIDENTS)} incidents indexed")
