updated:  2026-11-01T16:48:28-0500
mode:     done
idle-ticks: 0

probe-dirs: [ /Users/shawn/projects/llama/.claude/worktrees/player/antenna/public/assets, /Users/shawn/projects/llama/.claude/worktrees/player/antenna/test, /Users/shawn/projects/llama/.claude/worktrees/player/antenna/e2e, /Users/shawn/projects/llama/.claude/worktrees/player/.superpowers/sdd/player/final-rereview ]
proc-name:   node|chrome|Google Chrome|ffmpeg|python3|docker
proc-anchor: /Users/shawn/projects/llama/.claude/worktrees/player

in-flight: []

expected-git:
  - { repo: /Users/shawn/projects/llama/.claude/worktrees/player, head: 87690e883458884db03882401d4a2331b60a1892, may-advance: true }

stall: { check: yes, minutes: 25 }
alarm: notify.sh
on-last-sentinel: keep-ticking
