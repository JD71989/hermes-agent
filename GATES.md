# Gates: Guardian Economic Kernel repair

OWNS: hermes_cli/guardian_economic.py, hermes_cli/subcommands/guardian.py, hermes_cli/guardian_e2e.py, hermes_cli/guardian_supervisor.py, hermes_cli/guardian_scheduler.py, tools/bond_revenue_tool.py, tools/media_farm_tool.py, tests/**/test_guardian*, tests/tools/test_bond_revenue.py, tests/tools/test_media_farm_tool.py, tests/pionex/test_guardian_trading.py

Scope: Repair deterministic Guardian economic checks, idempotent accounting, subsystem integration, and live-trading locks without adding duplicate financial state.

- [ ] G1: EconomicKernel decisions and accounting are deterministic and persistable
  CHECK: scripts/run_tests.sh tests/tools/test_guardian_economic.py -q
  EXPECT: tests passed
  CWD: .
  EVIDENCE: pending

- [ ] G2: Guardian verification and synthetic mission preserve security-before-economics ordering
  CHECK: scripts/run_tests.sh tests/test_guardian_security.py tests/test_guardian_recovery.py tests/test_guardian_storage.py hermes_cli/guardian_e2e.py -q
  EXPECT: tests passed
  CWD: .
  EVIDENCE: pending

- [ ] G3: Financial subsystems remain credential-gated and live trading remains disabled
  CHECK: scripts/run_tests.sh tests/tools/test_bond_revenue.py tests/tools/test_media_farm_tool.py tests/pionex/test_guardian_trading.py -q
  EXPECT: tests passed
  CWD: .
  EVIDENCE: pending

- [ ] G4: Modified Python integration files compile and the focused suite passes
  CHECK: python -m py_compile hermes_cli/guardian_economic.py hermes_cli/subcommands/guardian.py hermes_cli/guardian_e2e.py hermes_cli/guardian_supervisor.py hermes_cli/guardian_scheduler.py tools/bond_revenue_tool.py tools/media_farm_tool.py tools/guardian_health.py agent/transports/chat_completions.py
  EXPECT: compile passed
  CWD: .
  EVIDENCE: pending
