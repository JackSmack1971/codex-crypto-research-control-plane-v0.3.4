#!/usr/bin/env bash
set -uo pipefail

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd -P)
POLICY="$ROOT/config/python-runtime-policy.json"
export PYTHONDONTWRITEBYTECODE=1

runtime_file=""
runtime_out=""
probe_only=false
allow_provision=false
script=""
test_candidates=""

while (($#)); do
  case "$1" in
    --runtime-file) runtime_file=$2; shift 2 ;;
    --runtime-out) runtime_out=$2; shift 2 ;;
    --probe-only) probe_only=true; shift ;;
    --allow-provision) allow_provision=true; shift ;;
    --test-candidate) test_candidates="${test_candidates}${test_candidates:+$'\n'}test_override|$2"; shift 2 ;;
    --) shift; break ;;
    -*) printf 'Unknown option: %s\n' "$1" >&2; exit 2 ;;
    *) script=$1; shift; break ;;
  esac
done
script_args=("$@")

json_escape() {
  local value=${1-}
  value=${value//\\/\\\\}; value=${value//\"/\\\"}
  value=${value//$'\n'/\\n}; value=${value//$'\r'/\\r}; value=${value//$'\t'/\\t}
  printf '%s' "$value"
}

policy_string() {
  sed -nE 's/^[[:space:]]*"'"$1"'"[[:space:]]*:[[:space:]]*"([^"]+)".*/\1/p' "$POLICY" | head -n 1
}

policy_bool() {
  sed -nE 's/^[[:space:]]*"'"$1"'"[[:space:]]*:[[:space:]]*(true|false).*/\1/p' "$POLICY" | head -n 1
}

minimum_version=$(policy_string minimum_version)
preferred_version=$(policy_string preferred_provision_version)
runtime_dir_rel=$(policy_string repo_runtime_dir)
repo_provision_allowed=$(policy_bool allow_repo_local_uv_provision)
checked_at() { date -u +%Y-%m-%dT%H:%M:%SZ; }

probes=()
provisioning=()
resolved=""
resolved_source=""
resolved_version=""
provisioned=false

add_probe() {
  probes+=("{\"source\":\"$(json_escape "$1")\",\"candidate\":\"$(json_escape "$2")\",\"status\":\"$3\",\"detail\":\"$(json_escape "$4")\"}")
}

join_json() {
  local IFS=,
  printf '%s' "$*"
}

probe_candidate() {
  local source=$1 candidate=$2 output marker executable version major minor
  [[ -n "$candidate" ]] || return 1
  if [[ "$candidate" == */* && ! -f "$candidate" ]]; then
    add_probe "$source" "$candidate" NOT_FOUND "candidate not present"
    return 1
  fi
  if [[ "$candidate" != */* ]] && ! command -v -- "$candidate" >/dev/null 2>&1; then
    add_probe "$source" "$candidate" NOT_FOUND "candidate not present"
    return 1
  fi
  output=$("$candidate" -B -c 'import sys; print("CODEX_RUNTIME\t%s\t%s" % (sys.executable, sys.version.split()[0]))' 2>&1)
  local exit_code=$?
  marker=$(printf '%s\n' "$output" | awk -F '\t' '$1=="CODEX_RUNTIME" {line=$0} END {print line}')
  if ((exit_code != 0)) || [[ -z "$marker" ]]; then
    add_probe "$source" "$candidate" FAILED "exit=$exit_code ${output: -600}"
    return 1
  fi
  IFS=$'\t' read -r _ executable version <<<"$marker"
  major=${version%%.*}; minor=${version#*.}; minor=${minor%%.*}
  if ((major < 3 || (major == 3 && minor < 11))); then
    add_probe "$source" "$candidate" TOO_OLD "version=$version minimum=$minimum_version"
    return 1
  fi
  if [[ ! -f "$executable" ]]; then
    add_probe "$source" "$candidate" FAILED "resolved executable missing: $executable"
    return 1
  fi
  resolved=$(CDPATH= cd -- "$(dirname -- "$executable")" && printf '%s/%s' "$PWD" "$(basename -- "$executable")")
  resolved_source=$source
  resolved_version=$version
  add_probe "$source" "$candidate" READY "version=$version resolved=$resolved"
  return 0
}

runtime_descriptor_candidate() {
  [[ -f "$runtime_file" ]] || return 1
  grep -Eq '"status"[[:space:]]*:[[:space:]]*"READY"' "$runtime_file" || return 1
  sed -nE 's/.*"resolved_executable"[[:space:]]*:[[:space:]]*"([^"]+)".*/\1/p' "$runtime_file" | head -n 1
}

find_runtime() {
  local candidate uv_dir
  if [[ -n "$runtime_file" ]]; then
    candidate=$(runtime_descriptor_candidate)
    if [[ -z "$candidate" ]]; then
      add_probe runtime_file "$runtime_file" FAILED "descriptor missing, not READY, or missing resolved_executable"
      return 1
    fi
    probe_candidate runtime_file "$candidate" && return 0
    return 1
  fi

  if [[ -n "$test_candidates" ]]; then
    while IFS='|' read -r source candidate; do
      probe_candidate "$source" "$candidate" && return 0
    done <<<"$test_candidates"
    return 1
  fi

  for candidate in "$ROOT/.venv/bin/python" "$ROOT/venv/bin/python"; do
    [[ -e "$candidate" ]] && probe_candidate repo_venv "$candidate" && return 0
  done
  for candidate in python3.14 python3.13 python3.12 python3.11; do
    command -v "$candidate" >/dev/null 2>&1 && probe_candidate versioned_path "$(command -v "$candidate")" && return 0
  done
  if command -v pyenv >/dev/null 2>&1; then
    while IFS= read -r candidate; do
      [[ -n "$candidate" ]] && probe_candidate pyenv_which "$candidate" && return 0
    done < <(for v in 3.14 3.13 3.12 3.11; do pyenv which "python$v" 2>/dev/null || true; done)
  fi
  if [[ $(policy_bool allow_uv_managed_scan) == true ]]; then
    for uv_dir in "$ROOT/$runtime_dir_rel" "${XDG_DATA_HOME:-$HOME/.local/share}/uv/python"; do
      [[ -d "$uv_dir" ]] || continue
      while IFS= read -r candidate; do
        probe_candidate uv_managed_scan "$candidate" && return 0
      done < <(find "$uv_dir" -type f \( -name python -o -name 'python3.*' \) -perm -u+x 2>/dev/null | sort -r)
    done
  fi
  if [[ $(policy_bool allow_path_python) == true ]]; then
    for candidate in python3 python; do
      command -v "$candidate" >/dev/null 2>&1 && probe_candidate path_enumeration "$(command -v "$candidate")" && return 0
    done
  fi
  if [[ $(policy_bool allow_uv_locator) == true ]] && command -v uv >/dev/null 2>&1; then
    candidate=$(uv python find ">=$minimum_version" --no-config --no-python-downloads 2>/dev/null || true)
    if [[ -n "$candidate" ]]; then
      probe_candidate uv_python_find "$candidate" && return 0
    else
      add_probe uv_python_find "$(command -v uv)" FAILED "uv found no existing Python >=$minimum_version"
    fi
  else
    add_probe uv_python_find uv NOT_FOUND "uv executable unavailable"
  fi
  return 1
}

provision_runtime() {
  local target started output exit_code
  if [[ "$repo_provision_allowed" != true || "$allow_provision" != true ]]; then return 1; fi
  if ! command -v uv >/dev/null 2>&1; then
    provisioning+=("{\"status\":\"SKIPPED\",\"reason\":\"UV_NOT_FOUND\"}")
    return 1
  fi
  target="$ROOT/$runtime_dir_rel"
  case "$target" in "$ROOT"/*) ;; *) provisioning+=("{\"status\":\"FAILED\",\"reason\":\"INSTALL_DIR_OUTSIDE_REPOSITORY\"}"); return 1 ;; esac
  mkdir -p -- "$target"
  started=$(checked_at)
  output=$(UV_PYTHON_INSTALL_REGISTRY=0 UV_PYTHON_INSTALL_BIN=0 uv python install "$preferred_version" --install-dir "$target" --no-bin --no-config 2>&1)
  exit_code=$?
  provisioning+=("{\"status\":\"$([[ $exit_code == 0 ]] && printf COMPLETED || printf FAILED)\",\"method\":\"uv_python_install\",\"requested_version\":\"$(json_escape "$preferred_version")\",\"install_dir\":\"$(json_escape "$target")\",\"started_at\":\"$started\",\"completed_at\":\"$(checked_at)\",\"exit_code\":$exit_code,\"detail\":\"$(json_escape "${output: -1200}")\"}")
  [[ $exit_code == 0 ]] && provisioned=true
}

write_result() {
  local json=$1
  if [[ -n "$runtime_out" ]]; then
    mkdir -p -- "$(dirname -- "$runtime_out")"
    printf '%s\n' "$json" >"$runtime_out"
  fi
  printf '%s\n' "$json"
}

if ! find_runtime; then
  provision_runtime || true
  if [[ "$provisioned" == true ]]; then
    test_candidates=""
    find_runtime || true
  fi
fi

if [[ -z "$resolved" ]]; then
  json="{\"status\":\"BLOCKED\",\"reason\":\"NO_WORKING_PYTHON_3_11_PLUS\",\"checked_at\":\"$(checked_at)\",\"minimum_version\":\"$(json_escape "$minimum_version")\",\"platform\":\"linux\",\"mode\":\"native\",\"repo_local_provision_allowed\":$repo_provision_allowed,\"provisioning_attempted\":$([[ ${#provisioning[@]} -gt 0 ]] && printf true || printf false),\"provisioning\":[$(join_json "${provisioning[@]}")],\"probes\":[$(join_json "${probes[@]}")],\"remediation\":[\"Inspect the recorded probe failures before changing the machine.\",\"Repair uv/network/filesystem execution or install CPython 3.11+ explicitly.\",\"Do not begin Massive acquisition until this probe returns READY.\"]}"
  write_result "$json"
  exit 127
fi

json="{\"status\":\"READY\",\"platform\":\"linux\",\"mode\":\"native\",\"source\":\"$(json_escape "$resolved_source")\",\"executable\":\"$(json_escape "$resolved")\",\"resolved_executable\":\"$(json_escape "$resolved")\",\"prefix\":[],\"version\":\"$(json_escape "$resolved_version")\",\"checked_at\":\"$(checked_at)\",\"provisioned_repo_runtime\":$provisioned,\"provisioning\":[$(join_json "${provisioning[@]}")],\"probes\":[$(join_json "${probes[@]}")]}"
if [[ -n "$runtime_out" ]]; then
  mkdir -p -- "$(dirname -- "$runtime_out")"
  printf '%s\n' "$json" >"$runtime_out"
fi
if [[ "$probe_only" == true ]]; then
  printf '%s\n' "$json"
  exit 0
fi
[[ -n "$script" ]] || { printf 'A repository Python script is required unless --probe-only is used.\n' >&2; exit 2; }
case "$(CDPATH= cd -- "$(dirname -- "$script")" 2>/dev/null && pwd -P)/$(basename -- "$script")" in
  "$ROOT"/*) ;;
  *) printf 'Script must resolve inside the active project root.\n' >&2; exit 2 ;;
esac
exec "$resolved" -B "$script" "${script_args[@]}"
