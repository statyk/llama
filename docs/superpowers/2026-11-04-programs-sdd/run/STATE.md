updated:  2026-11-04T05:19:32-0500
mode:     done
idle-ticks: 0

probe-dirs: [ /Users/shawn/projects/llama/.claude/worktrees/programs/packages/transmitter/src, /Users/shawn/projects/llama/.claude/worktrees/programs/packages/emcee/src, /Users/shawn/projects/llama/.claude/worktrees/programs/packages/llama/src, /Users/shawn/projects/llama/.claude/worktrees/programs/antenna/public, /Users/shawn/projects/llama/.claude/worktrees/programs/scripts ]
proc-name:   python3|python|node|pytest
proc-anchor: /Users/shawn/projects/llama/.claude/worktrees/programs

in-flight: []

expected-git:
  - { repo: /Users/shawn/projects/llama/.claude/worktrees/programs, head: 434c2637, may-advance: true }

stall: { check: yes, minutes: 25 }
alarm: notify.sh
on-last-sentinel: keep-ticking
