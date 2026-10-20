updated:  2026-10-20T12:17:12-0400
mode:     done
idle-ticks: 0
# writer: peer 14455d61-96ec-47d7-bf0b-86cfb6e7a6b5 (orch-r4)
# work in flight is shell commands (reapply waves / harness re-checks), logs teed into /Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1/.superpowers/sdd/tier1/orch-r4/

probe-dirs: [ /Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1/docs, /Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1/.superpowers/sdd/tier1/evid-rr1 ]
proc-name:   python3|python|Python
proc-anchor: /Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1

in-flight: []

expected-git:
  - { repo: /Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1, head: 4cd1ebc, may-advance: true }
  - { repo: /Users/shawn/projects/llama, head: f1744ad, may-advance: true }

stall: { check: yes, minutes: 40 }
alarm: notify.sh + PushNotification
on-last-sentinel: keep-ticking
