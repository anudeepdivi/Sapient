#!/usr/bin/env bash
# One benchmark run at a time (never two at once). Skips results that already exist; 3 tries each.
# Usage: bench/run_grid.sh "<results dirs>" "<arms>"      e.g. bench/run_grid.sh "v3 v3_run2 v3_run3" "ASEARCH"
cd "$(dirname "$0")/.."
LOG=bench/results/v3_grid.log
for dir in $1; do for arm in $2; do for ds in ADAE ADSL ADLBC ADTTE; do
  suffix=""; [ "$ds" != ADAE ] && suffix="_$(echo $ds | tr A-Z a-z)"
  out="bench/results/$dir/arm_$(echo $arm | tr A-Z a-z)$suffix.json"
  [ -f "$out" ] && continue
  runner=bench/run_arm_a.py; [ "$arm" = C ] && runner=bench/run_arm_c.py
  for try in 1 2 3; do
    echo "$(date '+%F %T') START $dir $arm $ds try=$try $SAPIENT_BENCH_MODEL" >> $LOG
    if SAPIENT_BENCH_RESULTS=$dir SAPIENT_BENCH_DATASET=$ds .venv/bin/python $runner $arm > "bench/results/$dir/run_${arm}_${ds}.out" 2>&1 && [ -f "$out" ]; then
      echo "$(date '+%F %T') DONE  $dir $arm $ds" >> $LOG; break
    fi
    echo "$(date '+%F %T') FAIL  $dir $arm $ds try=$try" >> $LOG; sleep 60
  done
done; done; done
