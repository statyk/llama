updated:  2026-10-25T20:22:20-0400
mode:     work
idle-ticks: 0

probe-dirs: [ /Users/shawn/projects/llama/.claude/worktrees/scheduler/packages/transmitter/src/transmitter, /Users/shawn/projects/llama/.claude/worktrees/scheduler/packages/transmitter/tests_transmitter, /Users/shawn/projects/llama/.claude/worktrees/scheduler/docs ]
proc-name:   python3|python|pytest|node|docker
proc-anchor: /Users/shawn/projects/llama/.claude/worktrees/scheduler

in-flight: []

expected-git:
  - { repo: /Users/shawn/projects/llama/.claude/worktrees/scheduler, head: dbd3601, may-advance: true }

stall: { check: yes, minutes: 25 }
alarm: notify.sh + PushNotification
on-last-sentinel: keep-ticking
