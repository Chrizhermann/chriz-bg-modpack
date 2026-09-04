# Third-party notices

## Project license

The first-party `chriz-bg-modpack` source and documentation are distributed under
the MIT License in `LICENSE`.

## WeiDU

The release archive includes the official WeiDU 249.00 Windows AMD64 executable,
renamed to `setup-chriz-bg-modpack.exe`. WeiDU is separate third-party software and
is distributed under the GNU General Public License version 2. The license text
from the official archive is included in the release as `WEIDU-COPYING.txt`.

- Release archive: https://github.com/WeiDUorg/weidu/releases/download/v249.00/WeiDU-Windows-249-amd64.zip
- Source: https://github.com/WeiDUorg/weidu/tree/v249.00
- Archive SHA-256: `b156910cbec69359fc2e42f6739aa959d49047d6fd3dc172f6bed88ffad8f927`
- Packaged executable source path: `WeiDU-Windows/weidu.exe`
- Executable SHA-256: `ad70f5897a6d0ba4b0d226f845a9b14cf345f56cc9697ca8d05cac9fe4932c1a`
- License source path: `WeiDU-Windows/COPYING`

WeiDU is not covered by this repository's MIT License.

## Compatibility research and factual attribution

This project interoperates with user-installed mods; it does not redistribute their
packages or assets.

- Component `440` addresses an installed-resource interaction involving
  [Ascension](https://github.com/Gibberlings3/Ascension) and EE Fixpack.
- Component `450` addresses an installed-resource interaction involving
  [Sword Coast Stratagems](https://github.com/Gibberlings3/SwordCoastStratagems)
  and EE Fixpack.
- Public Gibberlings Three forum investigation and a hotfix concept described by
  Dan_P informed the behavioral diagnosis for the shapechange interaction.

These are factual credits only. Components `440` and `450` are independently
implemented: no Ascension, SCS, EE Fixpack, or Dan_P hotfix source code, script
blocks, binary resources, artwork, or other payloads are copied into this project.

The owner's custom Sarah portrait is not distributed in this repository or release.
