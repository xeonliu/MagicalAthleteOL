# Playful race props

During a race, players and spectators can open **Interact**, choose another player (including a bot), and throw an egg or tomato. The dialog closes after throwing so the animated arc and splatter can be seen on the table. The latest throw is also shown in a compact line below the scores, including on the HTML/2D fallback.

The topbar entry occupies no permanent board space. Mobile uses a scrollable bottom dialog with large targets; desktop uses a centered dialog. The native dialog supports Escape, focus management, and background dismissal. Announcements and camera controls retain their own layout.

`THROW_PROP` carries `actionId`, `targetPlayerId`, and `item` (`egg` or `tomato`). The server validates membership, race phase, target, and a four-second per-sender cooldown. Successful action IDs are deduplicated; retries receive `ACTION_ACK`. The server broadcasts `PROP_THROWN` with a unique event ID, actor and target IDs/names, item, and `cooldownMs` to connected room participants.

These transient messages contain no game snapshot or revision. They do not update scores, positions, dice, decisions, timers, or the race playback queue. Cosmetic errors are handled separately from gameplay errors. Props do not survive a restart or play again on reconnect. At most four effects are mounted per client and they clear after 2.2 seconds; reduced-motion users see only a brief splash.

The prop meshes and splashes are native Three.js shapes. Eggs have a tapered shell, curved shell fragments, translucent white and a yellow yolk; tomatoes have lobed skin, a leafy calyx, pulp and seeds. Both leave an irregular stain on the target piece and a glossy puddle on the board while small droplets fall under cosmetic gravity. Reduced motion shows the settled splash without flight or scattering.

A collision callback plays the prop-specific Web Audio cue once when the projectile reaches its target: shell crack and wet landing for eggs, a softer squash and juice for tomatoes. Cues are deduplicated by throw ID, remain independent of music/art-pack selection, and do not replay from restored game state. The 2D fallback uses the same flight delay and cancels pending cues on leaving or reconnecting. Native offline audio checks verify a bounded, unclipped cue ending in silence. No new raster assets, external services, or gameplay physics are needed.
