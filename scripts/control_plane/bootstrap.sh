#!/usr/bin/env bash
set -uo pipefail

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd -P)
run_id=""; attempt_id=""; research_cutoff=""; out=""; runtime_out=""
while (($#)); do
  case "$1" in
    --run-id) run_id=$2; shift 2 ;;
    --attempt-id) attempt_id=$2; shift 2 ;;
    --research-cutoff) research_cutoff=$2; shift 2 ;;
    --out) out=$2; shift 2 ;;
    --runtime-out) runtime_out=$2; shift 2 ;;
    *) printf 'Unknown option: %s\n' "$1" >&2; exit 2 ;;
  esac
done
[[ -n "$run_id" && -n "$attempt_id" && -n "$research_cutoff" ]] || { printf '%s\n' 'Required: --run-id --attempt-id --research-cutoff' >&2; exit 2; }
out=${out:-"$ROOT/research/runs/$attempt_id.bootstrap.json"}
runtime_out=${runtime_out:-"$ROOT/research/runs/$attempt_id.python-runtime.json"}
[[ "$out" == /* ]] || out="$ROOT/$out"
[[ "$runtime_out" == /* ]] || runtime_out="$ROOT/$runtime_out"

json_escape() { local v=${1-}; v=${v//\\/\\\\}; v=${v//\"/\\\"}; v=${v//$'\n'/\\n}; v=${v//$'\r'/\\r}; v=${v//$'\t'/\\t}; printf '%s' "$v"; }
join_json() { local IFS=,; printf '%s' "$*"; }
checks=(); errors=(); warnings=()
add_check() { checks+=("{\"check\":\"$(json_escape "$1")\",\"status\":\"$2\"${3:+,\"detail\":\"$(json_escape "$3")\"}}"); }
add_error() { errors+=("\"$(json_escape "$1")\""); }
add_warning() { warnings+=("\"$(json_escape "$1")\""); }

required=(config/daily-capabilities.json config/daily-model.json config/massive-request-policy.json config/python-runtime-policy.json scripts/control_plane/massive_request_gate.py scripts/control_plane/materialize_mcp_dataset.py scripts/control_plane/evaluate_capabilities.py scripts/control_plane/validate_artifact.py scripts/pipeline/run_daily_pipeline.py scripts/control_plane/seal_acquisition.py scripts/control_plane/freeze_forecast.py)
for rel in "${required[@]}"; do
  if [[ -f "$ROOT/$rel" ]]; then add_check "required_file:$rel" PASS ""; else add_check "required_file:$rel" FAIL ""; add_error "missing:$rel"; fi
done

for rel in research/acquisitions research/data research/pipeline research/runs research/forecasts; do
  path="$ROOT/$rel"; probe="$path/.bootstrap-write-$$-$RANDOM"
  if mkdir -p -- "$path" 2>/dev/null && (umask 077; printf ok >"$probe") 2>/dev/null; then rm -f -- "$probe"; add_check "writable:$rel" PASS ""; else rm -f -- "$probe"; add_check "writable:$rel" FAIL "not writable"; add_error "not_writable:$rel"; fi
done

policy="$ROOT/config/massive-request-policy.json"
max=$(sed -nE 's/^[[:space:]]*"max_requests_per_window"[[:space:]]*:[[:space:]]*([0-9]+).*/\1/p' "$policy" | head -1)
window=$(sed -nE 's/^[[:space:]]*"window_seconds"[[:space:]]*:[[:space:]]*([0-9.]+).*/\1/p' "$policy" | head -1)
interval=$(sed -nE 's/^[[:space:]]*"minimum_interval_seconds"[[:space:]]*:[[:space:]]*([0-9.]+).*/\1/p' "$policy" | head -1)
if [[ -n "$max" && -n "$window" && -n "$interval" ]] && awk -v m="$max" -v w="$window" -v i="$interval" 'BEGIN { exit !(m>=1 && w>0 && i+1e-9>=w/m) }'; then
  add_check massive_request_policy PASS "$max call_api requests/$window s; minimum interval $interval s"
else add_check massive_request_policy FAIL "unsafe or unreadable pacing values"; add_error massive_request_policy_invalid; fi

prior=$(find "$ROOT/research/runs" -type f -name "*$run_id*.json" 2>/dev/null | wc -l | tr -d ' ')
if ((prior > 0)); then add_check prior_run_discovery WARN "$prior"; add_warning "prior_run_artifacts:$prior:create_new_attempt_do_not_overwrite"; else add_check prior_run_discovery PASS 0; fi

version=""; digest=""
[[ -f "$ROOT/VERSION" ]] && version=$(tr -d '\r\n' <"$ROOT/VERSION")
if [[ -f "$ROOT/CONTROL_PLANE_MANIFEST.json" ]] && command -v sha256sum >/dev/null 2>&1; then digest="sha256:$(sha256sum "$ROOT/CONTROL_PLANE_MANIFEST.json" | awk '{print $1}')"; fi
if [[ -n "$version" && -n "$digest" ]]; then add_check source_identity PASS "$version $digest"; else add_check source_identity WARN "VERSION or manifest digest unavailable"; add_warning source_identity_incomplete; fi

if command -v git >/dev/null 2>&1 && [[ -d "$ROOT/.git" ]]; then
  head=$(git -C "$ROOT" rev-parse HEAD 2>/dev/null || true)
  if [[ -n "$head" ]]; then add_check git_checkout PASS "$head"; else add_check git_checkout WARN "git head unavailable"; add_warning git_head_unavailable; fi
else add_check git_checkout WARN "not a Git checkout; source identity fallback recorded"; add_warning git_checkout_unavailable; fi

runtime_output=$("$SCRIPT_DIR/run_python.sh" --probe-only --runtime-out "$runtime_out" --allow-provision 2>&1)
runtime_exit=$?
if ((runtime_exit == 0)) && [[ -f "$runtime_out" ]]; then
  detail=$(sed -nE 's/.*"version":"([^"]+)".*"source":"([^"]+)".*"resolved_executable":"([^"]+)".*/\1 via \2: \3/p' "$runtime_out")
  add_check python_runtime PASS "${detail:-runtime descriptor READY}"
else add_check python_runtime FAIL "runtime probe exit $runtime_exit; inspect $runtime_out for diagnostics"; add_error python_runtime_unavailable; fi

add_warning 'massive_effective_access_probe_required:bootstrap cannot prove MCP entitlement'
status=READY; ((${#errors[@]})) && status=BLOCKED
mkdir -p -- "$(dirname -- "$out")"
json="{\"platform\":\"linux\",\"run_id\":\"$(json_escape "$run_id")\",\"attempt_id\":\"$(json_escape "$attempt_id")\",\"created_at\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"research_cutoff\":\"$(json_escape "$research_cutoff")\",\"status\":\"$status\",\"checks\":[$(join_json "${checks[@]}")],\"errors\":[$(join_json "${errors[@]}")],\"warnings\":[$(join_json "${warnings[@]}")],\"python_runtime_file\":\"$(json_escape "$runtime_out")\",\"source_version\":$([[ -n "$version" ]] && printf '\"%s\"' "$(json_escape "$version")" || printf null),\"control_plane_manifest_digest\":$([[ -n "$digest" ]] && printf '\"%s\"' "$digest" || printf null)}"
printf '%s\n' "$json" >"$out"
printf '%s\n' "$json"
[[ "$status" == READY ]] && exit 0 || exit 2
