updated:  2026-10-10T20:53:39-0400
mode:     done
idle-ticks: 0

probe-dirs: [ /Users/shawn/projects/llama/.claude/worktrees/playout-phase1/packages, /Users/shawn/projects/llama/.claude/worktrees/playout-phase1/antenna, /Users/shawn/projects/llama/.claude/worktrees/playout-phase1/docs ]
proc-name:   python3|python|pytest|ffmpeg|node|docker|workerd|npm
proc-anchor: /Users/shawn/projects/llama/.claude/worktrees/playout-phase1

in-flight:

expected-git:
  - { repo: /Users/shawn/projects/llama/.claude/worktrees/playout-phase1, head: 9fdc47a, may-advance: true }

stall: { check: yes, minutes: 25 }
alarm: notify.sh + PushNotification
on-last-sentinel: keep-ticking
