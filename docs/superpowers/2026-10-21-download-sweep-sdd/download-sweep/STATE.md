updated:  2026-10-21T04:25:37-0400
mode:     done
idle-ticks: 0

probe-dirs: [ /Users/shawn/projects/llama/.claude/worktrees/download-sweep/.superpowers/sdd/download-sweep/final-rerev, /Users/shawn/projects/llama/.claude/worktrees/download-sweep/packages/llama/src, /Users/shawn/projects/llama/.claude/worktrees/download-sweep/packages/llama/tests ]
proc-name:   python3|python|pytest
proc-anchor: /Users/shawn/projects/llama/.claude/worktrees/download-sweep

in-flight:

expected-git:
  - { repo: /Users/shawn/projects/llama/.claude/worktrees/download-sweep, head: 931d2dd, may-advance: true }

stall: { check: yes, minutes: 25 }
alarm: notify.sh + PushNotification
on-last-sentinel: keep-ticking
