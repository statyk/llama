"""llama.taper: the structure-only reader of the taper's set/encore markers.

Spec: docs/superpowers/specs/2026-10-22-taper-set-markers-design.md sections 1 and 2.

Every real-case literal below is copied verbatim, once, from
`~/.llama/cache/md_<identifier>.json` (the `description` field unless the comment says
`notes`); "excerpt" means a contiguous slice of that field. The comment names the show
slug and the cache file. The tests never read `~/.llama`.
"""

import pytest

from llama.models import ParsedSetlist, SetlistItem
from llama.setlist import parse_setlist
from llama.taper import TaperItem, TaperText, read_taper_structure, taper_text_for


def runs(tt: TaperText) -> list[str]:
    """The item labels with consecutive repeats collapsed: the structure, in order."""
    out: list[str] = []
    for item in tt.items:
        if not out or out[-1] != item.set:
            out.append(item.set)
    return out


def label(tt: TaperText, title: str) -> str:
    """The label of the one item with this title."""
    found = [i.set for i in tt.items if i.title == title]
    assert len(found) == 1, (title, found)
    return found[0]


def titles(tt: TaperText) -> list[str]:
    return [i.title for i in tt.items]


# ---------------------------------------------------------------------------------------
# Real-case excerpts
# ---------------------------------------------------------------------------------------

# acousticsyndicate-2005-05-29: md_as2005-05-29.sbd.flac16.json (description)
ACOUSTIC_SYNDICATE = (
    'Set 1\n'
    '1.  announcements/introduction\n'
    '2.  Believe\n'
    '3.  Prelude ->\n'
    '4.  Pumpkin & Daisy\n'
    '5.  Marie St. Lauriette\n'
    '6.  Fast train To Georgia\n'
    '7.  Fleeting Moments ->\n'
    '8.  Neighbors\n'
    '9.  Sweetest Breeze\n'
    '10. Sunlight Falls\n'
    '11. Carnival\n'
    '12. Hypocrite Smile\n'
    '13. They Come This Way\n'
    '14. Dancing To the Requiem\n'
    '15. North Country Girl\n'
    '16. Prayer for Solace >\n'
    '17. Long Way Round\n'
    '\n'
    'Set 2\n'
    '1.  Water of Love*\n'
    '2.  Critters*\n'
    '3.  Crazy Town*\n'
    '4.  Katie & Burl*\n'
    '5.  Pilot*\n'
    '6.  Better Place*\n'
    '7.  Wake\n'
    '8.  Why Not\n'
    '9.  No Woman No Cry/So Lonely\n'
    '10. Fly Swatter\n'
    '11. Sugaree\n'
    '12. Morning Dew\n'
    '13. Big Sciota\n'
    '14. Billy The Kid\n'
    '15. Heartbreaker tease\n'
    '16. No Time ->\n'
    '17. Sailor Suit\n'
    '18. Terra Firma\n'
    '19. Good While It Lasted\n'
    "20. Baba O'Riley\n"
    'encore:\n'
    '21. One More Dollar\n'
    '22. Brown Mountain Lights\n'
    '23. Rainbow Roller Coaster\n'
    '24. The Grind'
)

# derektrucksband-2006-01-25: md_dtb2006-01-25.flac16.json (description)
DTB_2006_01_25 = (
    'Disc 1 (Set One)\n'
    '01. Crow Jane\n'
    '02. Sahib Teri Bandi > Maki Madni > Sahib Teri Bandi\n'
    '03. I Wish I Knew\n'
    '04. Blind Crippled and Crazy\n'
    '05. Mahjoun >\n'
    '06. Greensleeves\n'
    '07. Sailing On >\n'
    '08. Key to the Highway\n'
    '\n'
    'Disc 2 (Set Two)\n'
    '01. Volunteered Slavery >\n'
    "02. I'll Find My Way\n"
    "03. Let's Go Get Stoned\n"
    '04. Chevrolet\n'
    '05. All I Do\n'
    '06. Maybe Your Baby\n'
    '07. Anyday\n'
    '08. Sonido Alegre\n'
    'Encore:\n'
    '09. Hook & Sling'
)

# radiators-1984-09-07: md_rad1984-09-07.flac16.json (description)
RADIATORS_1984 = (
    'Disc 1:\n'
    '[Set One]\n'
    "01.  You Can't Always Get What You Want                         \n"
    '02.  Hardcore->                                  \n'
    "03.  Shake Your Body (Down To The Ground)-> Pump It Up-> Trouble Comin' Every Day->"
    ' Hardcore\n'
    '04.  Hard Rock Kid     \n'
    '05.  Straight Eight                                        \n'
    '06.  Little Sadie                                          \n'
    '07.  Honey From The Bee\n'
    '08. Rainbow                                    \n'
    '09.  Law Of The Fish                   \n'
    '10.  Number Two Pencil             \n'
    '[Set Two]\n'
    '11.  Pass The Hatchet                         \n'
    '12.  Let The Red Wine Flow                     \n'
    "13.  Kickin' Mule          \n"
    '\n'
    'Disc 2:\n'
    '01.  Spanish Moon                       \n'
    '02.  One Eyed Jack                               \n'
    '03.  Nail Your Heart To Mine                          \n'
    '04.  Love Is A Tangle             \n'
    '05.  Red Dress                                            \n'
    '\n'
    '[Set Three]\n'
    '06.  Mustang Sally\n'
    '07.  Bad Taste                             \n'
    '08.  Raindancer                                      \n'
    '09.  Last Getaway                                   \n'
    '10.  Suck The Head                                 \n'
    '11.  Out In The Woods\n'
    "12.  You Can't Take It With You                \n"
    '13.  Slow Down'
)

# radiators-2008-01-25: md_rads2008-01-25.json (description, excerpt)
RADIATORS_2008 = (
    '~Set One~\n'
    '1. Intro\n'
    '2. You Cant Take It With You>\n'
    'You Aint Hittin On Nothin>\n'
    'Birthday>\n'
    'Little Bit Of Your Love>\n'
    'Land of One Thousand Dances>\n'
    'You Cant Take It With You\n'
    '3. One Eyed Jacks\n'
    '4. Join The Circus\n'
    '5. Dreaming Out Loud\n'
    '6. The End Is Not In Sight\n'
    '7. Cocktail Music\n'
    '8. Number Two Pencil\n'
    '9. Last Getaway\n'
    '10. You Cant Do that\n'
    '11. Light My Pipe\n'
    '12. Doctor Doctor\n'
    '~Set Two~\n'
    '1. Suck Da Head\n'
    '2. Dixie Chicken>\n'
    '     Goin Down The Road>\n'
    '3. He Aint Give You None>\n'
    'Chevy Thirty Nine\n'
    '4. Fools Go First\n'
    '5. Honey Bee>\n'
    '      Whip It On Me>\n'
    '      Create A Disturbance In Your Mind\n'
    '6. Lucinda>\n'
    'The Magnificent Seven>\n'
    'Sissy Strut\n'
    '7. Rosie\n'
    '8. Call Back\n'
    '~Encore~\n'
    '9. Out In The Woods\n'
    '10. Western Plains\n'
    '11. Outro'
)

# stantonmoore-2001-11-20: md_moore2001-11-20.flac16.json (description)
STANTON_MOORE = (
    'Disc 1:<br />\n'
    '<br />\n'
    '-Set I-<br />\n'
    '<br />\n'
    '1. intro<br />\n'
    '2. ?<br />\n'
    '3. Fire on the Bayou<br />\n'
    '4. Cissy Strut &gt; Look Ka Py Py<br />\n'
    '5. ?<br />\n'
    '6. Change Reform<br />\n'
    '<br />\n'
    '-Set II-<br />\n'
    '<br />\n'
    '7. intro<br />\n'
    '8. ?<br />\n'
    '<br />\n'
    'Disc 2:<br />\n'
    '<br />\n'
    '1. Hype &amp; the Hooplah<br />\n'
    '2. People Say<br />\n'
    '3. ? *<br />\n'
    '4. Red Hot Mama **<br />\n'
    '5. Hey Pocky Way<br />\n'
    '<br />\n'
    '-Encore-<br />\n'
    '<br />\n'
    '6. When Your Go to New Orleans'
)

# radiators-2003-03-14: md_rad2003-03-14.shnf.json (description)
RADIATORS_2003 = (
    '-DISC ONE-\n'
    '(Set 1)\n'
    '01) Tuning >\n'
    "02) Feel Like Rockin'\n"
    '03) New Empty\n'
    '04) Fever Dream\n'
    '05) Smoke And Dust\n'
    '06) Bring Me The Head Of Isaac Newton >\n'
    '07) Ace In The Hole >\n'
    '08) Tight Spot \n'
    '09) Murder In My Heart For The Judge\n'
    '10) Bad Taste\n'
    '11) Swamp Rat\n'
    '12) Lyla\n'
    "13) Devil's Dream\n"
    '\n'
    '-DISC TWO-\n'
    '(Set 1, cont.)\n'
    '01) Monkey In Her Heart\n'
    '02) Lost Radio\n'
    '(Set 2)\n'
    '03) Lowlife\n'
    '04) Sitting On Top Of The World > Third Stone From the Sun jam\n'
    '05) Kamikazee >\n'
    '06) Whole Lotta Love\n'
    "07) Frankie's B-Day\n"
    '08) Death Of The Blues\n'
    '\n'
    '-DISC THREE-\n'
    '(Set 2, cont.)\n'
    '01) The Cuckoo >\n'
    '02) Jam >\n'
    '03) Look-Ka Py Py\n'
    '04) Wild And Free\n'
    '05) Kenny >\n'
    '06) Magic Bus\n'
    '07) And We Bid You Goodnight >\n'
    "08) Keep On Poppin' That Shine"
)

# tealeafgreen-2005-05-14: md_tlg2005-05-14.flac16.json (description)
TEA_LEAF_GREEN = (
    'Disc 1\n'
    '\n'
    '01) Gasaholic\n'
    '02) Reservoir\n'
    '03) The Invasion >\n'
    '04) Precious Stone\n'
    '05) Taught To Be Proud >\n'
    '06) Hot Dog\n'
    '07) Planet of Green Love >\n'
    '08) Waiting For The Man#\n'
    '09) Country Seduction\n'
    '10) Vote on Tuesday\n'
    '\n'
    'Disc 2\n'
    '    \n'
    '(set II)\n'
    '01) The Garden (Part I) >\n'
    '02) The Garden (Part II) >\n'
    '03) The Garden (Part III)\n'
    '04) Georgie P\n'
    '05) Morning Sun >\n'
    '06) Panspermic De-evolution\n'
    '07) Incandescent Devil\n'
    '\n'
    'Disc 3\n'
    '\n'
    '(set II cont.)\n'
    "01) Who Am I (What's My Name)?*\n"
    "02) Sex in the 70's\n"
    '03) Pretty Jane\n'
    '04) Freedom\n'
    "05) I've Got a Feeling**\n"
    '(encore)\n'
    '06) Wet Spot\n'
    '07) Death Cake'
)

# newridersofthepurplesage-2005-12-16: md_nrps2005-12-16.flac16.json (description)
NRPS_2005_12_16 = (
    '01.  Lonesome LA Cowboy\n'
    "02.  I Don't Know You\n"
    '03.  Contract\n'
    '04.  Sunday Suzie\n'
    '05.  Garden Of Eden\n'
    '06.  Rainbow\n'
    '07.  Panama Red\n'
    '08.  Whiskey\n'
    '09.  Groupie\n'
    "10.  Runnin' Back To You\n"
    "11.  Truck Drivin' Man\n"
    '\n'
    'disc 2 (set 2):\n'
    '01.  Henry\n'
    '02.  Last Lonely Eagle\n'
    '03.  Dirty Business\n'
    '04.  Louisiana Lady\n'
    "05.  What You Gonna' Do\n"
    '06.  15 Days\n'
    '07.  Sutters Mill\n'
    '\n'
    'disc 3 (set 2 cont.):\n'
    '01.  Take A Letter Maria\n'
    '02.  Death & Destruction\n'
    '03.  Lochinvar\n'
    '04.  Willie & The Hand Jive\n'
    '05.  crowd\n'
    '06.  encore:  Rainy Day Woman\n'
    '07.  Ripple'
)

# darkstarorchestra-2005-11-16: md_dso2005-11-16-MIX.json (description)
DSO_2005_11_16 = (
    '1: \n'
    'Bertha\n'
    'Me and My Uncle\n'
    'Sugaree\n'
    'BIODTL\n'
    'Tennessee Jed\n'
    'LL Rain\n'
    'BE Women\n'
    'Jack Straw\n'
    'Row Jimmy\n'
    'WRS Prelude>\n'
    'WRS Part 1>\n'
    'Let it Grow\n'
    '\n'
    '2:\n'
    'Eyes>\n'
    'China Doll\n'
    'Set 2:\n'
    'Greatest \n'
    'Ramble on \n'
    'Big River\n'
    'Sing Your Blues Away\n'
    'China Cat>\n'
    'I Know You Rider\n'
    '\n'
    '3:\n'
    'El Paso\n'
    "He's Gone>\n"
    'Truckin>\n'
    'NFA>\n'
    'GDTRFB>\n'
    'NFA\n'
    '\n'
    'E: Stella Blue>\n'
    '   One More Saturday Night'
)

# darkstarorchestra-2004-04-20: md_dso040420.shnf.json (description)
DSO_2004_04_20 = (
    '1:\n'
    'Cold Rain> \n'
    'Minglewood, \n'
    "Dupree's, \n"
    'Far From Me, \n'
    'Me & My Uncle> \n'
    'Mexicali,\n'
    'Push, \n'
    'BIODTL, \n'
    'Bird Song, \n'
    'Music\n'
    '\n'
    '2:Scarlet> \n'
    'Fire, \n'
    'L. L. Rain> \n'
    'Eyes> \n'
    'Drumz> \n'
    '\n'
    '3:\n'
    'Space>\n'
    'Gimme Some Lovin> \n'
    'Wheel> \n'
    'Black Peter> \n'
    'Around> \n'
    'Good Lovin\n'
    'Encore: Black Muddy River\n'
    'Filler: Hey Pocky Way'
)

# darkstarorchestra-2005-12-03: md_dso2005-12-13-mix.json (description)
DSO_2005_12_03 = (
    '1:\n'
    'Intro\n'
    'Wheel*>\n'
    'Greatest*\n'
    'Lazy River Road**\n'
    'Mr Charlie\n'
    'Cassidy*\n'
    'Melody***\n'
    'Box of Rain**\n'
    'Esau@\n'
    "King Solomon's Marbles\n"
    "Rob Barraco's break\n"
    'Ripple*\n'
    '\n'
    '2:\n'
    'Let Me Sing Your Blues Away***\n'
    'Music*\n'
    'Ship of Fools**\n'
    'Dancin**\n'
    'Help*>\n'
    'Slipknot>\n'
    'Drumz>\n'
    '\n'
    '3:\n'
    'Space>\n'
    'WRS Prelude@>\n'
    'WRS Part 1@**>\n'
    'Let It Grow*\n'
    'Viola Lee Blues**>\n'
    'Sunrise**>\n'
    "Franklin's***\n"
    'Encore: Lucy In the Sky***>\n'
    'We Bid You Goodnight***\n'
)

# darkstarorchestra-2004-04-24: md_dso040424.shnf.json (description)
DSO_2004_04_24 = (
    '1:\n'
    'Bertha, \n'
    'Mama Tried, \n'
    'Loser, \n'
    'Big River, \n'
    "You Ain't Woman Enough, \n"
    'HC Sunshine, \n'
    'BT Wind, \n'
    'Rample On, \n'
    'Bobby McGee, \n'
    'BE Women, \n'
    'Around\n'
    '\n'
    '2:\n'
    'Scarlet, \n'
    'Me & My Uncle> \n'
    'FOTD, \n'
    'WRS Prelude> \n'
    'WRS Part 1> \n'
    'Let It Grow> \n'
    'Drums> \n'
    '\n'
    '3:\n'
    'Space>\n'
    'Other One> \n'
    'Dark Star> \n'
    'Comes A Time> \n'
    'Other One> \n'
    'Dark Star> \n'
    'Let it Grow> \n'
    'Uncle John> \n'
    'Sugar Magnolia\n'
    'Encore: Loose Lucy'
)

# gratefulshred-2023-11-10: md_gratefulshred2023-11-10.akg483.bsc1.json (description)
GRATEFUL_SHRED = (
    '<div>Grateful Shred</div><div>November 11, 2023</div><div>The Capitol'
    ' Theatre</div><div>Port Chester, NY</div><div>Taped by: Cam'
    ' Keough</div><div>Transferred by: Cam Keough</div><div>Source: 4 Track'
    ' Matrix</div><div>Source 1: AKG 480/CK63-&gt; Naiant Littlebox (OT)-&gt; Zoom'
    ' F6(32/48)</div><div>Source 2: Busman BSC-1(Omni) -&gt; Zoom'
    ' F-6(32/48)</div><div>Lineage: Adobe Audition-&gt; CD WAVE-&gt; THL</div><div>Location:'
    ' Right of soundboard about 7.5ft high</div><div><br /></div><div>Set 1:</div><div>01'
    ' Intro</div><div>02 Bertha</div><div>03 Greatest Story Ever Told</div><div>04 Cold Rain'
    " and Snow</div><div>05 France</div><div>06 Sitting In Limbo</div><div>07 Playin' In The"
    ' Band</div><div>08 The Music Never Stopped</div><div><br /></div><div>Set'
    " 2:</div><div>01 Intro/Tuning</div><div>02 Dancin 'In the Streets</div><div>03 Friend"
    ' Of The Devil</div><div>04 Big Iron</div><div>05 Eyes Of The World -&gt;</div><div>06'
    ' West LA Fadeaway</div><div>07 Cassidy</div><div>08 Here Comes Sunshine'
    ' -&gt;</div><div>09 Space -&gt;</div><div>10 To Lay Me Down</div><div>11 Alligator'
    ' -&gt; Drums</div><div>12 Going Down The Road Feeling Bad -&gt;</div><div>13 We Bid You'
    " Goodnight</div><div>14 E. Playin' Reprise</div><div>15 E. Queen Jane</div>"
)

# tedeschitrucksband-2019-02-16: md_ttb2019-02-16.json (description)
TTB_2019_02_16 = (
    'Set One<br /><br />01. Loving You Is Sweeter Than Ever<br />02. Walk Through This'
    " Life<br />03. Darlin' Be Home Soon<br />04. Let Me Get By<br />05. Right On Time<br"
    " />06. Down In The Flood<br />07. High & Mighty<br />08. Don't Keep Me Wondering<br"
    ' />09. Idle Wind<br /><br />Set Two<br /><br />10. Laugh About It<br />11. Sweet'
    ' Inspiration<br />12. Keep On Growing<br />13. Do I Look Worried<br />14. When Will I'
    " Begin<br />15. Leavin' Trunk<br />16. The Sky Is Crying<br />17. I Want More<br />18."
    " E: Let's Go Get Stoned"
)

# umphreysmcgee-2005-09-14: md_um2005-09-14.flac16.json (description)
UM_2005_09_14 = (
    'Disc 1\n'
    'Set 1\n'
    '1. Example 1\n'
    '2. Plunger\n'
    '3. 13 Days\n'
    '4. Out of Order\n'
    '5. Visions of Parin > "Jimmy Stewart" > Andy\'s Last Beer\n'
    '6. In Violation of Yes\n'
    "7. Baba O'Reily \n"
    '\n'
    'Disc 2\n'
    'Set 2\n'
    '1. Dump City\n'
    '2. Syncopated Strangers > Nothing 2 Fancy\n'
    '3. Resolution > Nopener\n'
    '\n'
    'Disc 3\n'
    "1. Tinkle's\n"
    '2. All in Time \n'
    '3. E: Higgins\n'
    "4. Can't Find My Way Home"
)

# gratefuldead-1990-03-22: md_gd1990-03-22.sbd.miller.107871.flac16.json (description)
GD_1990_03_22 = (
    'Set 1\n'
    '\n'
    'Feel Like A Stranger, West L.A. Fadeaway, Easy To Love You, Beat It On Down The Line,'
    " It Must Have Been The Roses, The Last Time, Picasso Moon, Don't Ease Me In\n"
    '\n'
    'Set 2\n'
    '\n'
    'Scarlet Begonias-> Fire On The Mountain, Samson & Delilah, Believe It Or Not,'
    " Truckin'-> Jam-> Drums-> Jam-> The Other One-> Hey Jude*-> Dear Mr. Fantasy-> Hey Jude"
    " Reprise-> Sugar Magnolia, E: It's All Over Now Baby Blue\n"
    '\n'
    '*The whole song sung by Brent'
)

# moe-1997-02-21: md_moe1997-02-21.flac16.json (description)
MOE_1997_02_21 = (
    'Disc One\t\t\t\n'
    'Set I\n'
    '\n'
    '01) tuning/banter\t\t\n'
    '02) Rebubula\t\t\t\n'
    '03) Spine Of A Dog\t\t\n'
    '04) Mexico\t\t\t\n'
    '05) Threw It All Away\t\t\n'
    '06) Stranger Than Fiction\t\n'
    '07) Timmy Tucker\t\t\n'
    '\n'
    '\n'
    'Disc Two\t\t\t\n'
    'Set II\n'
    '\n'
    '01) Brent Black\t\t\t\n'
    '02) Happy Hour Hero\t\t\n'
    '03) 32 Things\t\t\t\n'
    '04) It\t\t\t\t\n'
    '\n'
    '\n'
    'Disc Three\t\t\t\n'
    'Set II (cont.)\n'
    '\n'
    '01) Moth >\t\t\t\n'
    '02) Head >\t\t\t\n'
    '03) Interstellar Overdrive >\t\n'
    '04) Head >\t\t\t\n'
    '05) Moth\t\t\t\n'
    'Encore 1:\n'
    '06) tuning/banter\t\t\n'
    '07) Spaz Medicine\t\t\n'
    '08) Buster\t\n'
    'Encore 2:\n'
    '09) Seat Of My Pants'
)

# garciagrass-2010-10-23: md_garciagrass2010-10-23.digigal.flac16.json (description, excerpt)
GARCIA_GRASS = (
    'disc 01 [Set I]\n'
    '01\tTuning/Intro\n'
    '02\tPig In A Pen \n'
    '03\tBlue Yodel #9 \n'
    '04\tBird Song \n'
    '05\tLonesome LA Cowboy \n'
    '06\tGoing To The Races \n'
    '07\tTo Lay Me Down \n'
    '08\tThey Love Each Other \n'
    '09\tDark Hollow\n'
    '10\tSimple Twist Of Fate\n'
    "11\tI Ain't Broke But I'm Badly Bent\n"
    "12\tI'm On My Way Back To The Old Home\n"
    '13\tMidnight Moonlight\n'
    '\n'
    'disc 02 [Set II]\n'
    '01\tSet Break\n'
    '02\tHonky Tonk Blues \n'
    '03\tShady Grove \n'
    '04\tLonesome Fiddle Blues\n'
    '05\tBand Intros \n'
    "06\tI'm Troubled \n"
    '07\tWild Horses\n'
    '08\tOn And On\n'
    '09\tDeep Elem Blues\n'
    '10\tTangled Up In Blue\n'
    '11\tE1: The Hobo Song\n'
    "12\tE2: Rolling In My Sweet Baby's Arms"
)

# The Smashing Pumpkins 2007-07-16 (not in the library): md_tsp2007-07-16.dpa4061.mt.flac16.json (description, excerpt)
TSP_2007_07_16 = (
    'Disc 3 [50:53]\n'
    'Encore #1\n'
    "1. That's The Way (My Love is)\n"
    '2. Heavy Metal Machine\n'
    'Encore #2\n'
    '3. - Banter\n'
    '4. Zero\n'
    '5. Gossamer'
)

# umphreysmcgee-2004-04-14: md_um2004-04-14.shnf.json (description)
UM_2004_04_14 = (
    'Disc 1 - Set 1\n'
    '\n'
    '01. The Fuzz >\n'
    '02. "Jimmy Stewart" >\n'
    '03. The Fuzz\n'
    '04. Nothing Too Fancy >\n'
    '05. The Girl is Mine > Jane Says > The Girl is Mine >\n'
    '06. Nothing Too Fancy\n'
    '07. Wife Soup\n'
    '08. Slacker >\n'
    '09. Professor Wormbog >\n'
    '10. Slacker\n'
    '11. Divisions\n'
    '\n'
    '\n'
    'Disc 2 - Set 2\n'
    '\n'
    '01. Mail Package\n'
    '02. Front Porch >\n'
    '03. Resolution >\n'
    '04. Front Porch\n'
    '05. Thin Air\n'
    '\n'
    '\n'
    'Disc 3 - Set 2 + Encore\n'
    '\n'
    '01. The Stranger\n'
    '02. Walletsworth\n'
    '03. Ocean Billy\n'
    'e:\n'
    '04. Kabump >\n'
    '05. Nemo'
)

# lotus-2005-10-15: md_lotus2005-10-15.481.json (description)
LOTUS_2005_10_15 = (
    '~Disc 1: Set 1+Encore~\n'
    '\n'
    '01. Intro\n'
    '02. Livingston Storm\n'
    '03. Kesey Seed\n'
    '04. Travel\n'
    '05. Arupa\n'
    '06. Blue Giant\n'
    '07. Lucid Awakening\n'
    'Encore\n'
    '08. ~Encore Break~\n'
    '09. Nematode\n'
    '\n'
    '~Disc 2: Set 2~\n'
    '\n'
    '01. Intro\n'
    '02. Bubonic Tonic *\n'
    '03. Ball of Energy\n'
    '04. Sid\n'
    '05. Suitcases And Sandwiches \n'
    '06. Point/Electric Counterpoint\n'
    '07. Wax\n'
    '08. Sunrain\n'
    '\n'
    '* With Brandan on crazy dance moves\n'
    '\n'
    'I put the encore onto the end of disc 1 because it fit so comfortably onto 2 discs.'
    ' Enjoy!\n'
    '\n'
    'A Team Pittsburgh effort as usual!'
)

# u-melt-2007-06-22: md_umelt2007-06-22.sbd.flac16.json (description)
UMELT_2007_06_22 = (
    'U-Melt\n'
    '06-22-2007\n'
    'River St Jazz Cafe, Plains PA\n'
    '\n'
    'Disc 1 (Set 1)\n'
    '1. Red Star >\n'
    '2. Perfect World >\n'
    '3. Captain Delicious >\n'
    '4. Have A Cigar* >\n'
    '5. Captain Delicious >\n'
    '6. Song Behind the Time^ >\n'
    '7. The Eternal Groove >\n'
    '8. Sequel\n'
    '\n'
    'Disc 2 (Set 2)\n'
    '1. Ernest Funknine >\n'
    '2. A Portrait of Kismet >\n'
    '3. The Eternal Groove >\n'
    '4. A Robbins Tale Pt 1 >\n'
    '5. The Eternal Groove >\n'
    '6. A Robbins Tale Pt 2 >\n'
    '7. Escape >\n'
    '8. Sequel >\n'
    '\n'
    "Disc 3 (Set 2 cont'd)\n"
    '1. Red Star\n'
    '2. Banter\n'
    '3. E: Get Down On It'
)

# davidnelsonband-2007-09-07: md_dnf2007-09-07.DNF2007-09-07.KRALL-MATRIX.FLAC16.json (description)
DNB_2007_09_07 = (
    'David Nelson Band\n'
    'September 7, 2007\n'
    'Mexicali Blues\n'
    'Teaneck, NJ\n'
    '\n'
    'lineage:\n'
    '\n'
    'source 1\n'
    'CMXY4V (on stage) + KMR81i (fob) - SX-PR - Fostex FRE-2 (Oade sup mod)\n'
    '\n'
    'source 2\n'
    'Soundboard - 722 (24/48)\n'
    '\n'
    'Mixed and Dithered in Nuendo\n'
    '\n'
    'recorded & mixed by Robert Krall\n'
    '\n'
    'sonosaxATverizonDOTnet\n'
    '\n'
    'lineup:\n'
    '\n'
    'David Nelson- guitar vocals\n'
    'Barry Sless- guitar, pedal steel\n'
    'Mookie Siegel- Keyboards vocals\n'
    'Pete Sears- bass vocals\n'
    'John Molo- drums\n'
    '\n'
    '\n'
    '\n'
    'disc 1 \n'
    'set 1\n'
    '01. Fable of a Chosen One*\n'
    '02. Louis Collins*\n'
    '03. Friend of the Devil  \n'
    "04. Wizard's Son \n"
    '05. Rag Mama Rag\n'
    '06. Edge of the Wire\n'
    "07. Earl's Girls\n"
    '08.  encore: Box Of Rain (set 2)\n'
    '\n'
    'disc 2 \n'
    'set 2\n'
    '01. Wicked Messenger \n'
    '02. Into The Mystic\n'
    '03. Cut and Run  \n'
    '04. Road to Armageddon \n'
    '05. Stella Blue\n'
    '06. Kick In The Head\n'
    '\n'
    '*Source 2 only'
)

# stringcheeseincident-2004-06-19: md_sci2004-06-19.flac16.json (description)
SCI_2004_06_19 = (
    "Set 1:  One Step Closer, Rhum 'n' Zouc, Rhythm of the Road > 45th of November, Water,"
    " Sweet Melinda^ > Orion's Belt \n"
    ' \n'
    'Set 2:  This Must Be the Place (Naive Melody) > Jam > Desert Dawn, Joyful Sound, Miss'
    " Brown's Teahouse, Boo Boo's Pikanic, Dirk, Rivertrance¹ \n"
    ' \n'
    'Set 3:  Round the Wheel Intro > Valley of the Jig^ > Jams > Round the Wheel\n'
    '\n'
    'Set 4: Drums > Tye North Conducted Jam² > Search  \n'
    'Encore:  Salt Creek > Black Clouds  \n'
)

# paf2007-10-12.schoeps.taraszki.barfield.87850.flac24: md_paf2007-10-12.schoeps.taraszki.barfield.87850.flac24.json (description)
PAF_2007_10_12 = (
    'set 1 & 2, disc 1\n'
    '1 - good morning little schoolgirl\n'
    '2 - deal > jam >\n'
    '3 - mexican girl > jam >\n'
    '4 - scarlet begonias >\n'
    "5 - i'm so gone\n"
    '6 - turn on your lovelight\n'
    'set 2\n'
    '7 - lost highway\n'
    '8 - tell me mama\n'
    '9 - deep elem blues\n'
    '10- friend of the devil >\n'
    '11- big mon\n'
    '\n'
    'set 3, disc 2\n'
    "1 - playin' in the band >\n"
    '2 - cumberland blues >\n'
    "3 - uncle john's band > jam >\n"
    '4 - mountains of the moon >\n'
    '5 - terrapin station >\n'
    '6 - i know you rider\n'
    '7 - e: donor rap/intros\n'
    '8 - help on the way > slipknot! >\n'
    '9 - franklins tower'
)

# charliehunter-2001-12-08: md_CH2001-12-08.shnf.json (description)
CHARLIE_HUNTER = (
    'Early Show\n'
    '1. AC/DC\n'
    '2. Mestre Tata\n'
    '3. Two for Bleu\n'
    "4. Fat Fog's Hat Trick \n"
    '1. Mighty Mighty* \n'
    '2. Wade in the Water*\n'
    '3. The Spin Seekers\n'
    'Encore\n'
    '4. ? (New Song, Unt.)\n'
    '\n'
    'Late Show \n'
    '1. Mitch Better Have my Bunny\n'
    '2. Rythm Music Rides Again\n'
    '3. Philadelphia Hucklebuck\n'
    '4. Go Go Fantasy\n'
    '1. Mighty Mighty*\n'
    '2. Spoonful*\n'
    '3. Walk in the Light*\n'
    '4. Nostalgia in Times Square> Percussion Shuffle\n'
    'Encore\n'
    '5. La Plana'
)

# signalpath-2005-06-09: md_path2005-06-09.flac.json (description)
SIGNAL_PATH = (
    '1:  Escape Strategy\n'
    '2:  Kaleidoscope\n'
    '3:  W7\n'
    '4:  Bob It\n'
    '5:  Squisher\n'
    '6:  Transit\n'
    '7:  Wolves\n'
    '8:  ?\n'
    '9:  E: Bad Monkies'
)

# a sibling recording of moe-2002-06-22 (the one with the [1] footnotes): md_moe2002-06-22.akg481.dmic20.d8.flac16.json (description, excerpt)
MOE_2002_06_22_AKG481 = (
    '*Latenite Sets*\n'
    '\n'
    '~Set 1~ {1hr:59min:22sec}\n'
    '\n'
    '01. Set 1 Intro\n'
    '02. Plane Crash\n'
    '03. Mexico\n'
    '04. Bullet &gt;&gt;&gt;\n'
    "05. Kyle's Song &gt;&gt;&gt;\n"
    "06. Livin' Again &gt;&gt;&gt; [1]\n"
    '07. Meat [2]\n'
    '\n'
    '~Set 2~ {2hr:24min:56sec}\n'
    '\n'
    '01. Set 2 Intro\n'
    '02. Captain America &gt;&gt;&gt;\n'
    '03. Recreational Chemistry &gt;&gt;&gt; [3] [4]\n'
    '04. Happy Hour Hero &gt;&gt;&gt;\n'
    '05. Seat Of My Pants &gt;&gt;&gt;\n'
    '06. Sensory Deprivation Bank &gt;&gt;&gt;\n'
    '07. Four &gt;&gt;&gt; [5]\n'
    '08. Rebubula\n'
    'Encore\n'
    '09. Low [4] [6]\n'
    '10. Bring It Back Home [4] [6]\n'
    '\n'
    '[1] With "Creep" (Radiohead) tease.\n'
    '[2] With Robert Randolph on pedal steel guitar.\n'
    '[3] With Marc Brownstein and Aron Magner of the Disco Biscuits on bass and keyboards'
    ' for part of jam. Without Rob.\n'
    '[4] With Michael Travis of String Cheese Incident on percussion for part of jam.\n'
    '[5] With "Baby Elephant Walk" (Harry Mancini) tease.\n'
    '[6] With Michael Kang of String Cheese Incident on mandolin.'
)

# kinggizzardandthelizardwizard-2025-08-17: md_kglw2025-08-17.mk21-discocape.json (description, excerpt)
KGLW_2025_08_17 = (
    '<div>00. intro</div><div>01: Theia[1]</div><div>02. Sad Pilot[1]</div><div>03. Most Of'
    ' What I Like[1]</div><div>04. Aerodynamic[2]</div><div>05. Supercell</div><div>06.'
    ' Perihelion</div><div>07. Venusian 1</div><div>08. Her and I (Slow Jam 2)</div><div>09.'
    ' Motor Spirit</div><div>10. O.N.E.</div><div>11. Billabong Valley</div><div>12.'
    ' K.G.L.W. (Outro)</div><div>13. Sense[3] &gt;</div><div>14. Set</div><div>15. The'
    ' Silver Cord</div><div>16. The Garden Goblin</div><div>17. Daily Blues</div><div>18.'
    ' Float Along – Fill Your Lungs</div><div>19. The Dripping Tap[4]</div><div><br'
    ' /></div><div>Footnotes:</div><div>\xa0 \xa0 [1] Acoustic</div><div>\xa0 \xa0 [2] Acoustic; first'
    ' non-orchestra performance</div><div>\xa0 \xa0 [3] Synth arrangement</div><div>\xa0 \xa0 [4]'
    ' incomplete</div>'
)

# railroadearth-2008-08-17: md_rre2008-08-17.akg-dpa.json (description)
RRE_2008_08_17 = (
    'House/Live sound mix: Mike Partridge\n'
    '\n'
    '\n'
    'One Set\n'
    'Disc 1\n'
    '\n'
    '01.Intro\n'
    '02.Long Way To Go (A) (B)\n'
    '03.Seven Story Mountain\n'
    '04.Wade in the Water (A)\n'
    "05.Hard Livin' (A) (C)\n"
    "06.Came Up Smilin' (A) (C)\n"
    '\n'
    'Disc 2\n'
    '\n'
    '01.Goat (C) (D)\n'
    '02.1759 (D)\n'
    '03.All Alone (A) (C) (E)\n'
    '04.Bird in a House (A)\n'
    '05.Dance Around Molly -->\n'
    '06.Dandelion Wine\n'
    '07.Dandelion Wine (reprise)\n'
    '\n'
    '\n'
    '(A) With vocal harmonies by Sheryl Renee, Coco Brown\n'
    'and Shelly Lindsey\n'
    '(B) With horns: Dan Sears on trumpet and Dominic Lalli\n'
    'on alto saxophone\n'
    '(C) With horns: Dan Sears on trumpet, Dominic Lalli\n'
    'on alto saxophone and Bob Hemenger on tenor saxophone\n'
    '(D) With Scott Law on electric guitar\n'
    '(E) With Allie Kral on violin'
)

# a sibling recording of antibalasmusic-2003-04-28 (the one with the [1]...[5] track numbers): md_Antibalas2003-04-28.SBD.json (description, excerpt)
ANTIBALAS_2003_04_28_SBD = (
    '<div>DISC ONE:</div><div>\xa0</div><div>\xa0</div><div>[1] Battle Of The'
    ' Species</div><div>[2] Talkatif</div><div>[3] Na Fa Oyawo Mi</div><div>[4] Government'
    " Magic</div><div>[5] It's No Possible</div><div><br /></div><div>DISC"
    ' TWO:</div><div>[1]\xa0 Money Talks<br /></div><div>[2]\xa0 Who Is This America Dem Speak Of'
    " Today?</div><div>[3]\xa0 Elephant</div><div>[4]\xa0 Gba Mi Leti Ki N'Dolowo</div><div>[5]"
    ' N.E.S.T.A.</div>'
)

# a sibling recording of gratefuldead-1981-10-16 (the one with "Set I is Bobby and Jerry ..."): md_gd1981-10-16.147841.mtx.tobin.flac16.json (description)
GD_1981_10_16_TOBIN = (
    '<div>\n'
    '<div class="b1 set">\n'
    '<b>Set I</b>\n'
    '    <div class="set_info">\n'
    '        <span title="Click to edit" style="background-image:none;">Acoustic Set<br'
    ' /><br />\n'
    'On The Road Again<br />\n'
    'Dire Wolf<br />\n'
    'Monkey & The Engineer<br />\n'
    'Bird Song<br />\n'
    'Cassidy<br />\n'
    "Oh Babe It Ain't No Lie<br />\n"
    'The Race is On<br />\n'
    'Ripple</span>\n'
    '    </div>\n'
    '</div>\n'
    '\n'
    '<div class="b2 set">\n'
    '<b>Set II</b>\n'
    '    <div class="set_info">\n'
    '        <span title="Click to edit">Electric Set<br /><br />\n'
    'Playing In The Band ><br />\n'
    'Hully Gully ><br />\n'
    'The Wheel ><br />\n'
    'Samson & Delilah<br />\n'
    'Gloria ><br />\n'
    'Turn On Your Lovelight ><br />\n'
    "Goin' Down The Road Feeling Bad ><br />\n"
    'Playing In The Band Reprise ><br />\n'
    'Black Peter ><br />\n'
    'Sugar Magnolia</span></div>\n'
    '</div>\n'
    '\n'
    '<div class="b1 set">\n'
    '<br /><div class="set_info">\n'
    '        <span title="Click to edit" style="background-image:none;">\xa0</span></div>\n'
    '</div>\n'
    '\n'
    '<div class="b2 set">\n'
    '<b>Comment</b>\n'
    '    <div class="set_info">\n'
    '        <span title="Click to edit" style="background-image:none;">Set I is Bobby and'
    ' Jerry playing acoustic on borrowed instruments.<br /><br />\n'
    'Cindy Poris opened<br />\n'
    'No encore performed<br /><br />\n'
    'Jerry Garcia - Guitar<br />\n'
    'Bob Weir - Guitar<br />\n'
    'Brent Mydland - Keyboards<br />\n'
    'Phil Lesh - Bass<br />\n'
    'Bill Kreutzmann - Drums<br />\n'
    'Mickey Hart - Drums</span>\n'
    '    </div>\n'
    '</div>\n'
    '\n'
    '</div>'
)

# railroadearth-2009-01-15 (its notes field): md_rre2009-01-15.at4041.flac16.json (notes, excerpt)
RRE_2009_01_15_NOTES = (
    'Set One: -50:52.38-\n'
    '01 -04:19.36- Cold Water,\n'
    '02 -05:32.35- Ragtime Annie Lee,\n'
    '03 -04:53.41- Been Down This Road,\n'
    '04 -15:18.17- Head,\n'
    '05 -05:28.22- Crossing the Gap,\n'
    '06 -10:38.62- Colorado,\n'
    '07 -04:41.50- Right in Tune,\n'
    '\n'
    'Set Two: -83:41.71-\n'
    "08 -08:43.00- Little Bit O' Me,\n"
    '09 -03:25.02- Shockenawe Mountain Breakdown,\n'
    '10 -11:02.59- The Forecast,\n'
    "11 -07:10.29- Fisherman's Blues,\n"
    '12 -14:50.45- Warhead Boogie,\n'
    '13 -07:40.73- Bird in a House,\n'
    '14 -02:42.11- Dance Around Molly >\n'
    '15 -05:24.37- Dandelion Wine,\n'
    '16 -03:44.44- crowd\n'
    '17 -01:00.24- E: "Happy Birthday Jen",\n'
    '18 -10:56.42- Carrying Coal to Newcastle >\n'
    '19 -07:01.05- Mighty River'
)

# railroadearth-2009-01-15: md_rre2009-01-15.at4041.flac16.json (description)
RRE_2009_01_15_DESC = (
    '01 Cold Water,\n'
    '02 Ragtime Annie Lee,\n'
    '03 Been Down This Road,\n'
    '04 Head,\n'
    '05 Crossing the Gap,\n'
    '06 Colorado,\n'
    '07 Right in Tune,\n'
    "08 Little Bit O' Me,\n"
    '09 Shockenawe Mountain Breakdown,\n'
    '10 The Forecast,\n'
    "11 Fisherman's Blues,\n"
    '12 Warhead Boogie,\n'
    '13 Bird in a House,\n'
    '14 Dance Around Molly >\n'
    '15 Dandelion Wine,\n'
    '16 crowd\n'
    '17 E: "Happy Birthday Jen",\n'
    '18 Carrying Coal to Newcastle >\n'
    '19 Mighty River'
)

# a sibling recording of darkstarorchestra-2018-07-08: md_dso2018-07-08.r1.spyder9.flac16.json (description, excerpt)
DSO_2018_07_08 = (
    '<div>Set 1: (1:03:20)</div><div><br /></div><div>101. Intro &gt; Tuning</div><div>102.'
    ' Bertha &gt;</div><div>103. Good Lovin’</div><div>104. Dire Wolf &gt;</div><div>105. El'
    ' Paso</div><div>106. It Must’ve Been the Roses</div><div>107. New Minglewood'
    ' Blues</div><div>108. Ramble on Rose</div><div>109. Promised Land</div><div>110. Deal\xa0'
    ' \xa0 1</div><div><br /></div><div><br /></div><div>Set 2: (2:33:33)</div><div><br'
    ' /></div><div>201. Intro &gt;</div><div>202. Samson &amp; Delilah\xa0 \xa0 1</div><div>203.'
    ' Ship of Fools</div>'
)

# joerussosalmostdead-2018-02-15 (no description; its notes field): md_jrad2018-02-15.cmc621.cmc64.sbd.matrix.flac16.json (notes, excerpt)
JRAD_2018_02_15_NOTES = (
    '\tSet One (8:20PM - 9:45PM):\n'
    '01.  Jam @@ ->\n'
    '02.  Cassidy ## ->\n'
    '03.  Here Comes Sunshine @ ->\n'
    '04.  Not Fade Away # ->\n'
    '05.  Ruben & Cherise $ ->\n'
    '06.  Doin That Rag % (NA)\n'
    '07.  Magnificent Sanctuary Band ^\n'
    '\n'
    '\tSet Two (10:16PM - 11:53PM):\n'
    '01.  Eyes Of The World & ->\n'
    '02.  The Eleven * ->\n'
    '03.  Feel Like A Stranger ->\n'
    '04.  China Cat Sunflower ->\n'
    '05.  I Know You Rider >\n'
    '06.  The Other One\n'
    '\tEncore:\n'
    '07.  Shakedown Street'
)

# giantsand-1991-01-30: md_gsand1991-01-30.flac16.json (description)
GIANTSAND_1991_01_30 = (
    '1: Blanket For Tina\n'
    '2: Back To The Black and Grey\n'
    '3: Trickle Down System\n'
    '4: Picture Shows\n'
    '5: Still Too Far\n'
    '6: Romance of Falling\n'
    '7: Bible Black, Book II\n'
    "8: Can't Find Love\n"
    '9: Shadow To You\n'
    '10: Storm > Thin Line Man'
)

# giantsand-1989-05-10: md_gsand1989-05-10.flac16.json (description)
GIANTSAND_1989_05_10 = (
    '1: Interview..  \t \t \t\n'
    '2: Dreamville New Mexico\t\t\n'
    '3: Uneven Light Of Day \n'
    '4: Wearing The Robes Of Bible Black \n'
    '5: Mountain Of Love\n'
    "6: Almost The Politician's Wife\n"
    '7: Love Like A Train'
)

# giantsand-1996-02-03: md_gsand1996-02-03.flac16.json (description)
GIANTSAND_1996_02_03 = (
    'Disk 1\n'
    '\n'
    '1: \tGlum  \t\t\n'
    '2:\tRock & Roll Suicide \t\t\n'
    '3: \tGood and Gone \n'
    '4:      ---blank---\t\t\n'
    '5: \tScout (Calexico) \t\n'
    '6: \tSneaker (Calexico) \t\n'
    '7: \tWindjammer (Calexico) \t\n'
    '8: \tAngel of Death (Calexico) \t\n'
    '9: \tBlack Venetian Blind \t\t\n'
    "10: \tOl' 55 \t\t\n"
    '11: \tExplore You > Cold\t\t\n'
    '12: \tAll The Pretty Little Horses (Calexico)\n'
    '\n'
    'Disk 2\n'
    '\n'
    '1:  \tZen Monkey   \t\n'
    '2:\tSearchlight \t\n'
    '3: \tHush Little Baby \t\n'
    '4: \tHello Stranger  \t\n'
    '5:\tBack To Black & Grey \t\n'
    '6: \tPunishing Sun\n'
    '7: \tSatellite \t\n'
    '8: \tRainer Rise Up'
)

# giantsand-2001-01-08: md_gsand2001-01-08.flac16.json (description)
GIANTSAND_2001_01_08 = (
    '1: Blues Jam\n'
    '2: Wild Dog Waltz\n'
    '3: Snake Finger\n'
    '4: Out On The Weekend\n'
    '5: Mountain of Love\n'
    '6: Train Singer Song\n'
    '7: Wayfaring Stranger >\n'
    '8: Inner Flame \n'
    '9: Outro'
)

# giantsand-2001-03-04: md_gsand2001-03-04.flac16.json (description)
GIANTSAND_2001_03_04 = (
    '1: Four Door Maverick\n'
    '2: Chore of Enchantment\n'
    '3: Yer Ropes (Chicago Version)\n'
    '4: Piano Intermission\n'
    '5: Loretta and the Insect World\n'
    '6: Swerve\n'
    '7: Blue Marble Girl\n'
    '8: Inner Flame'
)

# giantsand-2004-10-15: md_gsand2004-10-15.flac16.json (description)
GIANTSAND_2004_10_15 = (
    'Disk 1\n'
    '\n'
    '1: Nod To Fred Neil\n'
    '2: Wonder (instrumental version)\n'
    '3: Remote (acoustic)\n'
    '4: Lovin Cup\n'
    '5: Yer Ropes\n'
    '6: Shiver\n'
    '7: No Reply\n'
    '8: Working On The Railroad\n'
    '9: The Farm\n'
    '10: The Uneven Light of Day\n'
    '11: Fool\n'
    '12: Muss\n'
    '13: Wayfaring Stranger\n'
    '14: Inner Flame\n'
    '15: Flying Around The Sun At Remarkable Speed\n'
    '16: Warm Storm\n'
    '17: Cracklin Water\n'
    '\n'
    'Disk 2\n'
    '\n'
    '1: Classico\n'
    '2: Remote (electric)\n'
    '3: Mope-A-Long\n'
    '4: Napoli\n'
    "5: Bored Lil' Devil"
)

# giantsand-2005-09-02: md_gsand2005-09-02.flac16.json (description)
GIANTSAND_2005_09_02 = (
    '1: Intro\n'
    '2: Get To Leave\n'
    '3: Steadfast\n'
    "4: Lovin' Cup\n"
    '5: Yer Ropes\n'
    '6: Down On Town \n'
    '7: Tumble and Tear\n'
    '8: Loretta and The Insect World\n'
    '9: Heartland\n'
    '10: Code Of The Road\n'
    '11: Wearing The Robes Of Bible Black\n'
    '12: Classico\n'
    '13: Shiver'
)

# calexico-1998-06-14: md_calexico1998-06-14.flac16.json (description)
CALEXICO_1998_06_14 = (
    '1: Instrumental/Sanchez >\n'
    '2: Trigger \n'
    '3: The Black Light \n'
    '4: The Blue\n'
    '5: Stray \n'
    '6: Taster\n'
    '7: Drape \n'
    '8: Return of The Manta Ray\n'
    '9: Slag'
)

# calexico-2000-07-01: md_calexico2000-07-01.flac16.json (description)
CALEXICO_2000_07_01 = (
    '1: Intro\n'
    '2: Wash \n'
    '3: The Ride, Part II \n'
    '4: Service & Repair \n'
    '5: Tulsa Telephone Book \n'
    '6: Fade \n'
    '7: Minas de Cobre \n'
    '8: Ballad of Cable Hogue \n'
    '9: Canción del Mariachi \n'
    '10: El Picador \n'
    '11: Frontera/Trigger \n'
    '12: Hey Baby, Qué Paso \n'
    '13: Stray \n'
    '14: Cascabel \n'
    '15: Crystal Frontier'
)

# calexico-2003-04-25: md_calexico2003-04-25.flac16.json (description)
CALEXICO_2003_04_25 = (
    'Disk 1\n'
    '\n'
    '1: Pepita \n'
    '2: Across the Wire \n'
    '3: Quattro \n'
    '4: Frontera/Trigger \n'
    '5: Dub Latina \n'
    '6: Sunken Waltz \n'
    '7: El Picador \n'
    '8: Not Even Stevie Nicks \n'
    '9: Fade \n'
    '10: Fatal Spring  >\n'
    '11: Close Behind \n'
    '12: Woven Birds \n'
    '13: Minas de Cobre \n'
    '14: Spokes \n'
    '15: Stray \n'
    '16: Corona \n'
    '17: Guero Canelo  \n'
    '\n'
    'Disk 2\n'
    '\n'
    '1: Black Heart    \n'
    '2: Falling Rain* \n'
    '3: Alone Again Or* \n'
    '4: Cancion Del Mariachi \n'
    '5: Crystal Frontier \n'
    '6: Attack El Robot! Attack!'
)


# a sibling recording of gratefuldead-1985-03-31: md_gd1985-03-31.sonyecm220t.keshavan.miller.106791.flac16.json (description)
GD_1985_03_31 = (
    'Set 1\n'
    '\n'
    'The Music Never Stopped, Candyman-> CC Rider-> Loser, Beat It On Down The Line,'
    " Dupree's Diamond Blues, It's All Over Now-> Don't Ease Me In\n"
    '\n'
    'Set 2\n'
    '\n'
    "Iko Iko-> Samson & Delilah-> He's Gone-> I Need A Miracle-> China Doll-> Drums-> The"
    " Wheel-> Playin' In The Band-> Day Tripper, E"
)

# Yonder Mountain String Band 2007-10-05 (not in the library): md_ymsb2007-10-05.Analog_Nagra_Reel_to_Reel.flac.json (description)
YMSB_2007_10_05 = (
    'Yonder Mountain String Band\n'
    '  SET 1:\n'
    '\n'
    ' \n'
    'Looking Back Over My Shoulder\n'
    'Southbound\n'
    'Damned If The Right One\n'
    'Night Out\n'
    'Cupid Shot Me Twice\n'
    'Jesus On The Mainline\n'
    'Things Youre Selling\n'
    'Boatmans Dance\n'
    '*Stealin\n'
    '*Ophelia\n'
    'Cuckoos Nest\n'
    'Dawn’s Early Light\n'
    'East Nashville Easter\n'
    '\n'
    '\n'
    'SET 2: \n'
    '\n'
    '\n'
    'Ruby\n'
    'Follow Me Down To The Riverside\n'
    'Ruby\n'
    'Mothers Only Son\n'
    'Not Far Away\n'
    'New Horizons\n'
    'Holdin\n'
    'New Horizons\n'
    'Belle Parker\n'
    'Troubled Mind\n'
    '20 Eyes\n'
    'Troubled Mind\n'
    'Sidewalk Stars\n'
    'Traffic Jam E\n'
    'Dim Lights Thick Smoke\n'
    '\n'
    '\n'
    '* The Wood Brothers on bass, guitar & vocals'
)


# ---------------------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------------------


def test_dataclasses_are_frozen():
    item = TaperItem(title="Bertha", set="1")
    with pytest.raises(AttributeError):
        item.set = "2"  # type: ignore[misc]


def test_worded_headers_assert_two_sets_and_encore():
    tt = read_taper_structure(ACOUSTIC_SYNDICATE)
    assert tt.asserts is True and tt.reason is None
    assert runs(tt) == ["1", "2", "encore"]
    assert tt.has_encore is True
    assert tt.encore_like is False
    assert tt.items[0] == TaperItem("Believe", "1")  # "announcements/introduction" is filler
    assert label(tt, "Long Way Round") == "1"
    assert label(tt, "Water of Love") == "2"
    assert label(tt, "Baba O'Riley") == "2"
    assert label(tt, "One More Dollar") == "encore"
    assert [i.set for i in tt.items].count("encore") == 4


def test_disc_with_set_headers():
    tt = read_taper_structure(DTB_2006_01_25)
    assert tt.asserts is True
    assert runs(tt) == ["1", "2", "encore"]
    sets = [i.set for i in tt.items]
    # Set 2 starts exactly at the first song under "Disc 2 (Set Two)".
    assert tt.items[sets.index("2")].title == "Volunteered Slavery"
    assert tt.items[sets.index("2") - 1].title == "Key to the Highway"
    assert label(tt, "Hook & Sling") == "encore"


def test_disc_slash_and_dash_set_forms():
    text = "Disc 1 / Set 1\nBertha\nSugaree\nDisc 2 - Set II\nScarlet Begonias\nFire On The Mountain\n"
    tt = read_taper_structure(text)
    assert tt.asserts is True
    assert [(i.title, i.set) for i in tt.items] == [
        ("Bertha", "1"), ("Sugaree", "1"),
        ("Scarlet Begonias", "2"), ("Fire On The Mountain", "2"),
    ]


def test_decorated_headers():
    # [Set One] / [Set Two] / [Set Three]
    tt = read_taper_structure(RADIATORS_1984)
    assert tt.asserts is True and runs(tt) == ["1", "2", "3"]
    assert label(tt, "Kickin' Mule") == "2"
    assert label(tt, "Spanish Moon") == "2"  # "Disc 2:" changes nothing
    assert label(tt, "Mustang Sally") == "3"
    # ~Set One~ / ~Set Two~ / ~Encore~
    tt = read_taper_structure(RADIATORS_2008)
    assert tt.asserts is True and runs(tt) == ["1", "2", "encore"]
    assert label(tt, "Suck Da Head") == "2"
    assert label(tt, "Out In The Woods") == "encore"
    # -Set I- / -Set II- / -Encore-
    tt = read_taper_structure(STANTON_MOORE)
    assert tt.asserts is True and runs(tt) == ["1", "2", "encore"]
    assert label(tt, "Hype & the Hooplah") == "2"
    assert label(tt, "When Your Go to New Orleans") == "encore"
    # Own-line (Set 1) / (Set 1, cont.) / (Set 2) / (Set 2, cont.)
    tt = read_taper_structure(RADIATORS_2003)
    assert tt.asserts is True and runs(tt) == ["1", "2"]
    assert label(tt, "Lost Radio") == "1"
    assert label(tt, "Lowlife") == "2"
    assert label(tt, "The Cuckoo") == "2"
    # Own-line (set II) after an unlabelled disc; (set II cont.); (encore)
    tt = read_taper_structure(TEA_LEAF_GREEN)
    assert tt.asserts is True and runs(tt) == ["1", "2", "encore"]
    assert label(tt, "Vote on Tuesday") == "1"
    assert label(tt, "The Garden (Part I)") == "2"
    assert label(tt, "Wet Spot") == "encore"


def test_mid_line_parenthetical_set_is_not_a_marker():
    text = "Set 1:\nBertha\nPlayin' In The Band (set II)\nSet 2:\nSugaree\nMorning Dew\n"
    tt = read_taper_structure(text)
    assert tt.asserts is True
    assert label(tt, "Playin' In The Band (set II)") == "1"
    assert label(tt, "Sugaree") == "2"


def test_leading_block_is_set_one_only_before_set_two():
    # An unlabelled block, then "disc 2 (set 2):": the block is set 1.
    tt = read_taper_structure(NRPS_2005_12_16)
    assert tt.asserts is True and runs(tt) == ["1", "2", "encore"]
    assert tt.items[0] == TaperItem("Lonesome LA Cowboy", "1")
    assert label(tt, "Truck Drivin' Man") == "1"
    assert label(tt, "Henry") == "2"
    # An unlabelled block, then "Set II:".
    tt = read_taper_structure("Bertha\nSugaree\nSet II: Scarlet Begonias > Fire On The Mountain\n")
    assert tt.asserts is True
    assert [(i.title, i.set) for i in tt.items] == [
        ("Bertha", "1"), ("Sugaree", "1"),
        ("Scarlet Begonias", "2"), ("Fire On The Mountain", "2"),
    ]
    # Lines before an explicit "Set 1:" are header text and produce no items.
    tt = read_taper_structure(GRATEFUL_SHRED)
    assert tt.items[0] == TaperItem("Bertha", "1")  # "01 Intro" is filler
    assert "Grateful Shred" not in titles(tt)
    assert "The Capitol Theatre" not in titles(tt)
    assert not any(t.startswith("Location") for t in titles(tt))
    # A leading block before "Set 2" with no song in it is no set 1: set 1 is skipped.
    tt = read_taper_structure("Set 2:\nSugaree\nSet 3:\nMorning Dew\n")
    assert tt.asserts is False and tt.reason == "void: skipped set number"


def test_track_prefix_stripped_before_markers():
    # "18. E: Let's Go Get Stoned"
    tt = read_taper_structure(TTB_2019_02_16)
    assert tt.asserts is True and runs(tt) == ["1", "2", "encore"]
    assert tt.has_encore is True
    assert label(tt, "I Want More") == "2"
    assert label(tt, "Let's Go Get Stoned") == "encore"
    assert "18." not in titles(tt) and "" not in titles(tt)
    # "3. E: Higgins"
    tt = read_taper_structure(UM_2005_09_14)
    assert tt.asserts is True and runs(tt) == ["1", "2", "encore"]
    assert label(tt, "All in Time") == "2"
    assert label(tt, "Higgins") == "encore"
    assert label(tt, "Can't Find My Way Home") == "encore"
    # "3. Encore: Higgins"
    tt = read_taper_structure("Set 1:\n1. Plunger\nSet 2:\n2. Tinkle's\n3. Encore: Higgins\n")
    assert tt.asserts is True
    assert [(i.title, i.set) for i in tt.items] == [
        ("Plunger", "1"), ("Tinkle's", "2"), ("Higgins", "encore"),
    ]
    # A prefixed encore line with no colon: only the prefix strip makes it a marker.
    tt = read_taper_structure("Set 1:\n01. Bertha\nSet 2:\n02. Sugaree\n03. Encore\n04. Ripple\n")
    assert tt.has_encore is True and label(tt, "Ripple") == "encore"


def test_inline_encore_marker():
    tt = read_taper_structure(GD_1990_03_22)
    assert tt.asserts is True and runs(tt) == ["1", "2", "encore"]
    assert tt.has_encore is True
    assert label(tt, "Sugar Magnolia") == "2"
    assert label(tt, "It's All Over Now Baby Blue") == "encore"
    assert tt.items[-1].set == "encore"


def test_numbered_encore_lines_continue():
    # "Encore 1:" ... "Encore 2:" is one encore; "Set II (cont.)" continues set 2.
    tt = read_taper_structure(MOE_1997_02_21)
    assert tt.asserts is True and runs(tt) == ["1", "2", "encore"]
    assert label(tt, "Interstellar Overdrive") == "2"
    assert [i.title for i in tt.items if i.set == "encore"] == [
        "Spaz Medicine", "Buster", "Seat Of My Pants",
    ]
    # "E1:" ... "E2:"
    tt = read_taper_structure(GARCIA_GRASS)
    assert tt.has_encore is True
    assert [i.title for i in tt.items if i.set == "encore"] == [
        "The Hobo Song", "Rolling In My Sweet Baby's Arms",
    ]
    assert "11" not in titles(tt) and "12" not in titles(tt)
    # "Encore #1" ... "Encore #2"
    tt = read_taper_structure(TSP_2007_07_16)
    assert [(i.title, i.set) for i in tt.items] == [
        ("That's The Way (My Love is)", "encore"), ("Heavy Metal Machine", "encore"),
        ("Zero", "encore"), ("Gossamer", "encore"),
    ]
    # "1st Encore:" ... "2nd Encore:"
    tt = read_taper_structure(
        "Set 1: Bertha\nSet 2: Sugaree\n1st Encore: Ripple\n2nd Encore: Brokedown Palace\n")
    assert tt.asserts is True and runs(tt) == ["1", "2", "encore"]
    assert label(tt, "Brokedown Palace") == "encore"


def test_set_and_encore_disc_line_asserts_nothing():
    # "Disc 3 - Set 2 + Encore" changes no label; the later "e:" starts the encore.
    tt = read_taper_structure(UM_2004_04_14)
    assert tt.asserts is True and runs(tt) == ["1", "2", "encore"]
    assert label(tt, "Thin Air") == "2"
    assert label(tt, "The Stranger") == "2"
    assert label(tt, "Ocean Billy") == "2"
    assert label(tt, "Kabump") == "encore"
    assert label(tt, "Nemo") == "encore"
    # "~Disc 1: Set 1+Encore~" names a set and the encore (`Disc N: Set M` is a recognised
    # shape since the Checkpoint A ruling (c)), so it asserts nothing and changes no label;
    # the later "Encore" starts the encore. "~Disc 2: Set 2~" is now recognised too, and as
    # a numbered marker after the encore it voids the structure. (Before ruling (c) neither
    # disc line was a form at all, and the text read as "one set".)
    tt = read_taper_structure(LOTUS_2005_10_15)
    assert tt.has_encore is True
    assert tt.encore_like is True  # the set-and-encore header names an encore
    assert label(tt, "Lucid Awakening") == "1"
    assert label(tt, "Nematode") == "encore"
    assert tt.asserts is False and tt.reason == "void: numbered marker after the encore"
    # "Set One & Encore" asserts nothing either.
    tt = read_taper_structure(
        "Set 1:\nBertha\nSet 2:\nSugaree\nSet 2 & Encore\nScarlet Begonias\nE: Ripple\n")
    assert tt.asserts is True
    assert label(tt, "Scarlet Begonias") == "2"
    assert label(tt, "Ripple") == "encore"


def test_set_and_encore_line_is_neither_a_set_start_nor_an_item():
    tt = read_taper_structure("Set 1:\nBertha\nSet 2 & Encore\nSugaree\nE: Ripple\n")
    assert "Set 2 & Encore" not in titles(tt)
    assert label(tt, "Sugaree") == "1"  # the line starts no set 2
    assert label(tt, "Ripple") == "encore"
    assert tt.asserts is False and tt.reason == "one set"


def test_continuation_header_asserts_nothing():
    # "disc 3 (set 2 cont.):"
    tt = read_taper_structure(NRPS_2005_12_16)
    assert label(tt, "Sutters Mill") == "2"
    assert label(tt, "Take A Letter Maria") == "2"
    assert label(tt, "Willie & The Hand Jive") == "2"
    assert label(tt, "Rainy Day Woman") == "encore"
    # "Disc 3 (Set 2 cont'd)"
    tt = read_taper_structure(UMELT_2007_06_22)
    assert tt.asserts is True and runs(tt) == ["1", "2", "encore"]
    assert [i.set for i in tt.items if i.title == "Red Star"] == ["1", "2"]
    assert label(tt, "Get Down On It") == "encore"
    # "Set 2 continued"
    tt = read_taper_structure("Set 1:\nBertha\nSet 2:\nSugaree\nSet 2 continued\nMorning Dew\n")
    assert tt.asserts is True and label(tt, "Morning Dew") == "2"


@pytest.mark.parametrize(
    "text, reason",
    [
        ("Set 1:\nBertha\nSet 2:\nSugaree\nSet 1:\nRipple\n", "void: decreasing set number"),
        ("Set 2:\nSugaree\nSet 1:\nRipple\n", "void: skipped set number"),
        ("Set 1:\nBertha\nSet 3:\nSugaree\n", "void: skipped set number"),
        ("Set 1:\nSet 2:\nSugaree\n", "void: empty set"),
        ("Set 1:\nTuning\nSet 2:\nSugaree\n", "void: empty set"),  # filler is no song
        ("Set 1:\nBertha\nSet 2:\nSugaree\nEncore:\n", "void: empty set"),
        ("Set 1:\nBertha\nSet 2:\nSugaree\nE: Ripple\nSet 3:\nMorning Dew\n",
         "void: numbered marker after the encore"),
        ("Set 1:\nBertha\nSet 2 cont.\nSugaree\n", "void: continuation without its set's header"),
        ("Set 1:\nBertha\nSet 2:\nSugaree\nSet IV:\nRipple\n", "void: set 4 or higher"),
        ("Set 1:\nBertha\nSet 2:\nSugaree\nSet Four: Ripple\n", "void: set 4 or higher"),
        ("Set 1:\nBertha\nSet 2:\nSugaree\nthe 4th set was all covers\n", "void: set 4 or higher"),
    ],
)
def test_void_rules_synthetic(text, reason):
    tt = read_taper_structure(text)
    assert tt.asserts is False
    assert tt.reason == reason


def test_void_rules():
    # "08.  encore: Box Of Rain (set 2)" is an encore line (the inline split, then the
    # track-prefix strip); the later "set 2" is a numbered marker after the encore.
    tt = read_taper_structure(DNB_2007_09_07)
    assert tt.asserts is False
    assert tt.reason == "void: numbered marker after the encore"
    assert label(tt, "Box Of Rain (set 2)") == "encore"
    # "Set 4:"
    tt = read_taper_structure(SCI_2004_06_19)
    assert tt.asserts is False and tt.reason == "void: set 4 or higher"
    # A continuation header and a header line carrying inline songs are not empty sets.
    tt = read_taper_structure("Set 1: Bertha, Sugaree\nSet 2:\nSet 2 continued\nMorning Dew\n")
    assert tt.asserts is True and tt.reason is None
    assert tt.items == (
        TaperItem("Bertha", "1"), TaperItem("Sugaree", "1"), TaperItem("Morning Dew", "2"))


def test_cross_check_against_parse_setlist():
    # parse_setlist reads "set 3, disc 2" as set 3; the reader's header shape does not.
    assert "3" in {i.set for i in parse_setlist(PAF_2007_10_12).items}
    tt = read_taper_structure(PAF_2007_10_12)
    assert runs(tt) == ["1", "2", "encore"]  # "set 1 & 2, disc 1" is no header either
    assert tt.asserts is False
    assert tt.reason == "cross-check: 3"


def test_one_set_or_encore_only_asserts_nothing():
    tt = read_taper_structure("Set 1:\nBertha\nSugaree\nMorning Dew\n")
    assert tt.asserts is False and tt.reason == "one set"
    tt = read_taper_structure("Bertha\nSugaree\nEncore: Ripple\n")
    assert tt.asserts is False and tt.reason == "one set" and tt.has_encore is True
    # "Early Show"/"Late Show" plus an encore only.
    tt = read_taper_structure(CHARLIE_HUNTER)
    assert tt.asserts is False and tt.reason == "one set"
    assert tt.has_encore is True
    assert "Early Show" in titles(tt)  # not a marker


@pytest.mark.parametrize(
    "text",
    [
        GIANTSAND_1991_01_30, GIANTSAND_1989_05_10, GIANTSAND_1996_02_03,
        GIANTSAND_2001_01_08, GIANTSAND_2001_03_04, GIANTSAND_2004_10_15,
        GIANTSAND_2005_09_02, CALEXICO_1998_06_14, CALEXICO_2000_07_01,
        CALEXICO_2003_04_25,
    ],
)
def test_n_colon_tracklists_are_not_markers(text):
    tt = read_taper_structure(text)
    assert tt.asserts is False and tt.reason == "no markers"
    assert tt.has_encore is False
    assert {i.set for i in tt.items} == {"1"}
    # The titles are parse_setlist's, less the `N:` prefix the reader strips (Checkpoint A,
    # item 4: `08: Ripple`); stripping it gives the line no meaning as a marker.
    import re as _re
    parsed = [_re.sub(r"^\s*\d{1,3}:\s+(?=\S)", "", i.title) for i in parse_setlist(text).items]
    assert titles(tt) == [t for t in parsed if t in titles(tt)]


def test_signalpath_n_colon_is_not_a_marker():
    tt = read_taper_structure(SIGNAL_PATH)
    assert tt.asserts is False and tt.reason == "one set"
    # Checkpoint A, item 4: the reader strips the `1:` prefix (was "1:  Escape Strategy").
    assert tt.items[0] == TaperItem("Escape Strategy", "1")
    # Only the inline "E:" is a marker; the "9:" stub it leaves is no item.
    assert tt.items[-1] == TaperItem("Bad Monkies", "encore")
    assert "9:" not in titles(tt)


@pytest.mark.parametrize("text", [DSO_2004_04_20, DSO_2005_12_03, DSO_2004_04_24])
def test_dso_bare_digit_disc_lines_are_not_markers(text):
    tt = read_taper_structure(text)
    assert not any(t.strip().rstrip(":").isdigit() for t in titles(tt))
    assert tt.asserts is False and tt.reason == "one set"  # an encore marker alone
    assert runs(tt) == ["1", "encore"]


def test_dso_bare_digit_lines_with_worded_set_two():
    tt = read_taper_structure(DSO_2005_11_16)
    assert not any(t.strip().rstrip(":").isdigit() for t in titles(tt))
    assert tt.asserts is True and runs(tt) == ["1", "2", "encore"]
    # The bare "2:" is no marker: "Eyes" and "China Doll" stay in the leading block.
    assert label(tt, "China Doll") == "1"
    assert label(tt, "Greatest") == "2"
    assert label(tt, "El Paso") == "2"  # the bare "3:" is no marker either
    assert label(tt, "Stella Blue") == "encore"


def test_footnote_and_track_number_brackets_are_not_markers():
    # "[1] With ..." footnotes after an "Encore" line stay in the encore.
    tt = read_taper_structure(MOE_2002_06_22_AKG481)
    assert tt.has_encore is True
    after = [i.set for i in tt.items[[t for t in titles(tt)].index("Low [4] [6]"):]]
    assert set(after) == {"encore"}
    assert any(t.startswith("[1] With") for t in titles(tt))
    tt = read_taper_structure(KGLW_2025_08_17)
    assert tt.asserts is False and tt.reason == "no markers" and tt.has_encore is False
    assert "Set" in titles(tt)  # "14. Set" is a song
    # "[1] ... [5]" track numbers on each of two discs.
    tt = read_taper_structure(ANTIBALAS_2003_04_28_SBD)
    assert tt.asserts is False and tt.reason == "no markers"
    assert titles(tt)[0] == "[1] Battle Of The Species"


def test_parenthesised_e_footnote_is_not_a_marker():
    tt = read_taper_structure(RRE_2008_08_17)
    assert tt.has_encore is False
    assert tt.asserts is False and tt.reason == "no markers"  # "One Set" is no marker
    assert "(E) With Allie Kral on violin" in titles(tt)


@pytest.mark.parametrize(
    "line, title, encore_like",
    [
        ("E.Ville", "E.Ville", True),  # a line starting "E." is encore-like (veto input)
        ("B. E. Women", "B. E. Women", False),
        ("E. Rutherford, NJ", "E. Rutherford", True),
        ("I Know You Rider", "I Know You Rider", False),
        ("J", "J", False),
        ("Untitled #12", "Untitled #12", False),
        ("E-Bow the Letter", "E-Bow the Letter", False),
        ("(E)", "(E)", True),
        # Ruling R4 (c): an own-line "[E]" is still no marker and still a set-1 title,
        # but it is now encore-like (was pinned as a plain title before fix round 1).
        ("[E]", "[E]", True),
        ("E.", "E.", True),
    ],
)
def test_title_lookalikes_are_not_markers(line, title, encore_like):
    tt = read_taper_structure(f"Set 1:\nBertha\n{line}\nSet 2:\nSugaree\n")
    assert tt.asserts is True
    assert tt.has_encore is False
    assert runs(tt) == ["1", "2"]
    assert label(tt, title) == "1"
    assert tt.encore_like is encore_like


def test_enumerated_digit_leading_title_keeps_its_number():
    # The track prefix is stripped ONCE, as `_emit_items` strips it: "02 100 Years" is
    # "100 Years", not "Years" (fix round 1, finding 1).
    text = ("Set 1:\n01 Bertha\n02 100 Years\n03 Sugaree\n"
            "Set 2:\n04 72 (This Highway's Mean)\n05 Ripple\n")
    tt = read_taper_structure(text)
    assert titles(tt) == [i.title for i in parse_setlist(text).items]
    assert label(tt, "100 Years") == "1"
    assert label(tt, "72 (This Highway's Mean)") == "2"


def test_duration_lookalike_is_not_a_marker():
    tt = read_taper_structure("Set 1:\nBertha\n1:08:07\nSet 2:\nSugaree\n")
    assert tt.asserts is True and runs(tt) == ["1", "2"]
    assert titles(tt) == ["Bertha", "Sugaree"]  # timestamp-only: neither marker nor item


def test_set_i_prose_is_not_a_marker():
    # "Set I is Bobby and Jerry playing acoustic on borrowed instruments." sits after
    # "Set II": it is a song line, not a return to set 1.
    tt = read_taper_structure(GD_1981_10_16_TOBIN)
    assert label(tt, "Set I is Bobby and Jerry playing acoustic on borrowed instruments.") == "2"
    assert runs(tt) == ["1", "2"]
    # parse_setlist numbers "Acoustic Set"/"Electric Set" as labelled sets, so its labels
    # include a set 3 the reader's structure lacks: the cross-check means no assertion.
    assert tt.asserts is False and tt.reason == "cross-check: 3"


def test_set_intro_is_not_set_one_and_set_iv_voids():
    tt = read_taper_structure("Set 1:\nBertha\nSet 2:\nSet Intro\nSugaree\n")
    assert tt.asserts is True and runs(tt) == ["1", "2"]
    assert "Set Intro" not in titles(tt)  # filler, and not a marker
    tt = read_taper_structure("Set 1:\nBertha\nSet 2:\nSugaree\nSet IV\nRipple\n")
    assert tt.asserts is False and tt.reason == "void: set 4 or higher"


@pytest.mark.parametrize(
    "tail",
    [
        "encore break\nRipple\n",
        "Ripple (Encore)\n",
        "(E)Spectacle\n",
        "Ripple enc\n",
        "E1 Ripple\n",
        "E) Ripple\n",
        "Encores were cut\n",
        "Set 2 & Encore\nRipple\n",  # names the encore without starting it
    ],
)
def test_encore_like_flag(tail):
    tt = read_taper_structure("Set 1:\nBertha\nSet 2:\nSugaree\n" + tail)
    assert tt.has_encore is False
    assert tt.encore_like is True


def test_encore_like_words_in_a_marker_lines_songs_count():
    tt = read_taper_structure("Set 1: Bertha\nSet 2: Sugaree, Ripple (Encore)\n")
    assert tt.has_encore is False and tt.encore_like is True


def test_encore_like_flag_real_case():
    # "14 E. Playin' Reprise": "E." is no marker, but it is encore-like.
    tt = read_taper_structure(GRATEFUL_SHRED)
    assert tt.has_encore is False
    assert tt.encore_like is True
    assert tt.asserts is True  # the veto itself is applied at placement, not here
    assert label(tt, "E. Playin' Reprise") == "2"


def test_encore_like_bare_e_item():
    # Ruling R4 (a): a split song item that is exactly "E" ("... Day Tripper, E").
    tt = read_taper_structure(GD_1985_03_31)
    assert tt.has_encore is False
    assert tt.encore_like is True
    assert tt.items[-1] == TaperItem("E", "2")  # still an item, and no encore starts


@pytest.mark.parametrize("tail", ["Sugaree, E2\n", "Sugaree, ENC\n", "Sugaree > enc\n",
                                  "[E]\n", "Sugaree, e\n"])
def test_encore_like_bare_e_item_forms(tail):
    tt = read_taper_structure("Set 1:\nBertha\nSet 2:\nScarlet Begonias\n" + tail)
    assert tt.has_encore is False and tt.encore_like is True


def test_encore_like_trailing_e_on_a_song_line():
    # Ruling R4 (b): a song line ending " E" ("Traffic Jam E").
    tt = read_taper_structure(YMSB_2007_10_05)
    assert tt.has_encore is False
    assert tt.encore_like is True
    assert label(tt, "Traffic Jam E") == "2"


@pytest.mark.parametrize("tail", ["US Blues (E)\n", "US Blues [E]\n", "US Blues E\n",
                                  "US Blues,E\n"])
def test_encore_like_trailing_e_forms(tail):
    tt = read_taper_structure("Set 1:\nBertha\nSet 2:\nSugaree\n" + tail)
    assert tt.has_encore is False and tt.encore_like is True


def test_encore_like_trailing_e_collateral_is_accepted():
    # Ruling R4 (b) collateral, accepted: a title ending " E" ("D to E") raises the veto
    # input too. It only makes the taper own less.
    tt = read_taper_structure("Set 1:\nBertha\nSet 2:\nD to E\nSugaree\n")
    assert tt.has_encore is False and tt.encore_like is True
    assert tt.asserts is True and label(tt, "D to E") == "2"


def test_encore_like_line_start_after_a_bare_track_number():
    # Ruling R4 (d): "14 E. Playin' Reprise" on a NON-enumerated text (one numbered line,
    # so `_NUM_PREFIX` does not apply) is encore-like too.
    tt = read_taper_structure("Set 1:\nBertha\nSet 2:\nSugaree\n14 E. Playin' Reprise\n")
    assert tt.has_encore is False and tt.encore_like is True
    assert label(tt, "14 E. Playin' Reprise") == "2"


def test_encore_like_new_rules_negatives():
    assert read_taper_structure("Set 1:\nBertha\nSet 2:\nE-Bow the Letter\n").encore_like is False
    assert read_taper_structure(
        "Set 1:\nBertha\nSet 2:\nEyes of the World\nGrateful Dawg\n").encore_like is False
    assert read_taper_structure(DTB_2006_01_25).encore_like is False


def test_encore_like_flag_false_on_a_clean_text():
    assert read_taper_structure(RADIATORS_2003).encore_like is False
    assert read_taper_structure("Set 1:\nBertha\nSet 2:\nSugaree\n").encore_like is False
    # A recognised encore marker is not itself encore-like text.
    assert read_taper_structure(ACOUSTIC_SYNDICATE).encore_like is False


def test_leading_timestamp_and_disc_number_items_dropped():
    # "07 -04:41.50- Right in Tune," and "Set One: -50:52.38-" (railroadearth notes)
    tt = read_taper_structure(RRE_2009_01_15_NOTES)
    assert label(tt, "Right in Tune") == "1"
    assert titles(tt)[0] == "Cold Water"
    assert not any(":" in t and t.replace(":", "").replace(".", "").strip("-").isdigit()
                   for t in titles(tt))
    assert tt.asserts is True and runs(tt) == ["1", "2", "encore"]
    # "Set 2: (2:33:33)" (and "Set 1: (1:03:20)")
    tt = read_taper_structure(DSO_2018_07_08)
    assert "(2:33:33)" not in titles(tt) and "(1:03:20)" not in titles(tt)
    assert titles(tt)[0] == "Bertha"
    assert label(tt, "Ship of Fools") == "2"
    # A bare "2:" line is no item (and no marker).
    tt = read_taper_structure("Set 1:\nBertha\n2:\nSugaree\nSet 2:\nScarlet Begonias\n")
    assert titles(tt) == ["Bertha", "Sugaree", "Scarlet Begonias"]
    assert label(tt, "Sugaree") == "1"


def test_taper_text_for_prefers_description():
    meta = {"description": "Set 1: Bertha\nSet 2: Sugaree", "notes": "Set One: Ripple"}
    assert taper_text_for(meta) == ("Set 1: Bertha\nSet 2: Sugaree", "description")
    # An encore marker alone is a marker: the description still wins.
    meta = {"description": "Bertha\nE: Ripple", "notes": "Set One\nBertha\nSet Two\nRipple"}
    assert taper_text_for(meta) == ("Bertha\nE: Ripple", "description")
    meta = {"description": "Bertha\nSugaree", "notes": "Set One\nBertha\nSet Two\nSugaree"}
    assert taper_text_for(meta) == ("Set One\nBertha\nSet Two\nSugaree", "notes")
    meta = {"description": "Bertha\nSugaree", "notes": ["Set One", "Bertha", "Set Two", "Sugaree"]}
    assert taper_text_for(meta) == ("Set One\nBertha\nSet Two\nSugaree", "notes")
    assert taper_text_for({"description": "Bertha", "notes": "Thanks to the taper"}) == ("", "none")
    assert taper_text_for({}) == ("", "none")
    # A description given as a list joins with newlines too.
    meta = {"description": ["Set 1: Bertha", "Set 2: Sugaree"]}
    assert taper_text_for(meta) == ("Set 1: Bertha\nSet 2: Sugaree", "description")


def test_taper_text_for_real_cases():
    # No description at all: the notes carry the markers.
    text, source = taper_text_for({"notes": JRAD_2018_02_15_NOTES})
    assert (text, source) == (JRAD_2018_02_15_NOTES, "notes")
    # The description's inline "17 E: ..." is a recognised marker, so the description is
    # read and the notes' "Set One:"/"Set Two:" are not (spec section 1's source rule).
    meta = {"description": RRE_2009_01_15_DESC, "notes": RRE_2009_01_15_NOTES}
    assert taper_text_for(meta) == (RRE_2009_01_15_DESC, "description")


# Captured on main @ a26c4d1 (taper-base worktree) before this task: parse_setlist's
# output for three of the excerpts above, as (confidence, [(title, normalized, set,
# segue), ...]).
PARSE_SETLIST_ON_MAIN = {
    "TTB_2019_02_16": (
        'high',
        [
            ('Loving You Is Sweeter Than Ever', 'loving you is sweeter than ever', '1', False),
            ('Walk Through This Life', 'walk through this life', '1', False),
            ("Darlin' Be Home Soon", 'darlin be home soon', '1', False),
            ('Let Me Get By', 'let me get by', '1', False),
            ('Right On Time', 'right on time', '1', False),
            ('Down In The Flood', 'down in the flood', '1', False),
            ('High & Mighty', 'high mighty', '1', False),
            ("Don't Keep Me Wondering", 'dont keep me wondering', '1', False),
            ('Idle Wind', 'idle wind', '1', False),
            ('Laugh About It', 'laugh about it', '2', False),
            ('Sweet Inspiration', 'sweet inspiration', '2', False),
            ('Keep On Growing', 'keep on growing', '2', False),
            ('Do I Look Worried', 'do i look worried', '2', False),
            ('When Will I Begin', 'when will i begin', '2', False),
            ("Leavin' Trunk", 'leavin trunk', '2', False),
            ('The Sky Is Crying', 'the sky is crying', '2', False),
            ('I Want More', 'i want more', '2', False),
            ("Let's Go Get Stoned", 'lets go get stoned', 'encore', False),
        ],
    ),
    "GD_1990_03_22": (
        'high',
        [
            ('Feel Like A Stranger', 'feel like a stranger', '1', False),
            ('West L.A. Fadeaway', 'west l a fadeaway', '1', False),
            ('Easy To Love You', 'easy to love you', '1', False),
            ('Beat It On Down The Line', 'beat it on down the line', '1', False),
            ('It Must Have Been The Roses', 'it must have been the roses', '1', False),
            ('The Last Time', 'the last time', '1', False),
            ('Picasso Moon', 'picasso moon', '1', False),
            ("Don't Ease Me In", 'dont ease me in', '1', False),
            ('Scarlet Begonias', 'scarlet begonias', '2', True),
            ('Fire On The Mountain', 'fire on the mountain', '2', False),
            ('Samson & Delilah', 'samson delilah', '2', False),
            ('Believe It Or Not', 'believe it or not', '2', False),
            ("Truckin'", 'truckin', '2', True),
            ('Jam', 'jam', '2', True),
            ('Drums', 'drums', '2', True),
            ('Jam', 'jam', '2', True),
            ('The Other One', 'the other one', '2', True),
            ('Hey Jude', 'hey jude', '2', True),
            ('Dear Mr. Fantasy', 'dear mr fantasy', '2', True),
            ('Hey Jude Reprise', 'hey jude reprise', '2', True),
            ('Sugar Magnolia', 'sugar magnolia', '2', False),
            ("It's All Over Now Baby Blue", 'its all over now baby blue', 'encore', False),
            ('The whole song sung by Brent', 'the whole song sung by brent', 'encore', False),
        ],
    ),
    "PAF_2007_10_12": (
        'high',
        [
            ('& 2', '2', '1', False),
            ('- good morning little schoolgirl', 'good morning little schoolgirl', '1', False),
            ('- deal', 'deal', '1', True),
            ('jam', 'jam', '1', True),
            ('- mexican girl', 'mexican girl', '1', True),
            ('jam', 'jam', '1', True),
            ('- scarlet begonias', 'scarlet begonias', '1', True),
            ("- i'm so gone", 'im so gone', '1', False),
            ('- turn on your lovelight', 'turn on your lovelight', '1', False),
            ('- lost highway', 'lost highway', '2', False),
            ('- tell me mama', 'tell me mama', '2', False),
            ('- deep elem blues', 'deep elem blues', '2', False),
            ('10- friend of the devil', '10 friend of the devil', '2', True),
            ('11- big mon', '11 big mon', '2', False),
            ("- playin' in the band", 'playing in the band', '3', True),
            ('- cumberland blues', 'cumberland blues', '3', True),
            ("- uncle john's band", 'uncle johns band', '3', True),
            ('jam', 'jam', '3', True),
            ('- mountains of the moon', 'mountains of the moon', '3', True),
            ('- terrapin station', 'terrapin station', '3', True),
            ('- i know you rider', 'i know you rider', '3', False),
            ('-', '', '3', False),
            ('donor rap/intros', 'donor rap intros', 'encore', False),
            ('- help on the way', 'help on the way', 'encore', True),
            ('slipknot!', 'slipknot', 'encore', True),
            ('- franklins tower', 'franklins tower', 'encore', False),
        ],
    ),
}


@pytest.mark.parametrize("name", sorted(PARSE_SETLIST_ON_MAIN))
def test_parse_setlist_unchanged(name):
    """(pin) parse_setlist's output is byte-identical to main's on real excerpts."""
    confidence, rows = PARSE_SETLIST_ON_MAIN[name]
    expected = ParsedSetlist(
        items=[SetlistItem(title=t, normalized=n, set=s, segue=g) for t, n, s, g in rows],
        confidence=confidence,
    )
    assert parse_setlist(globals()[name]) == expected


# ---------------------------------------------------------------------------------------
# Task 2: exact placement and the ownership decision
# ---------------------------------------------------------------------------------------

from llama.models import Track  # noqa: E402
from llama.songs import GD_SHORTHAND  # noqa: E402
from llama.taper import decide_taper, place_taper_structure  # noqa: E402


def mk(titles_: list[str], sources: dict[int, str] | None = None) -> list[Track]:
    sources = sources or {}
    return [Track(index=i + 1, set="1", title=t, filename=f"t{i + 1:02d}.mp3",
                  title_source=sources.get(i + 1, "tags")) for i, t in enumerate(titles_)]


def tt_of(*items: tuple[str, str]) -> TaperText:
    return TaperText(items=tuple(TaperItem(t, s) for t, s in items), asserts=True,
                     has_encore=any(s == "encore" for _, s in items), encore_like=False,
                     reason=None)


def place(tracks, taper, aliases=None, today=None):
    return place_taper_structure(tracks, taper, aliases=aliases or {},
                                 today_sets=today or ["1"] * len(tracks))


BASE_TAPER = tt_of(("Bertha", "1"), ("Let It Grow", "1"), ("Scarlet Begonias", "2"),
                   ("Truckin", "2"))


def base_tracks(between: list[str]) -> list[Track]:
    return mk(["Bertha", "Let It Grow", *between, "Scarlet Begonias", "Truckin"])


def test_places_when_both_sides_match_uniquely_with_filler_between():
    tracks = mk(["Bertha", "a1", "b1", "c1", "d1", "e1", "Let It Grow", "tuning",
                 "Scarlet Begonias", "Truckin"])
    taper = tt_of(("Bertha", "1"), ("Let It Grow", "1"), ("Scarlet Begonias", "2"),
                  ("Truckin", "2"))
    # the unmatched middle tracks are not in the taper's list; they are just tape tracks
    p = place(tracks, taper)
    assert not isinstance(p, str), p
    assert p.boundaries == (7,)
    assert p.sets == ("1",) * 7 + ("2",) * 3


def test_filler_keeps_todays_split_point():
    tracks = mk(["Let It Grow", "tuning", "banter", "Scarlet Begonias"])
    taper = tt_of(("Let It Grow", "1"), ("Scarlet Begonias", "2"))
    p = place(tracks, taper, today=["1", "1", "2", "2"])
    assert not isinstance(p, str), p
    assert p.boundaries == (2,)
    assert p.sets == ("1", "1", "2", "2")
    p = place(tracks, taper, today=["1"] * 4)
    assert p.boundaries == (1,)


def test_non_filler_between_is_unplaced():
    for mid in ("Donor Rap", "Space"):
        r = place(base_tracks([mid]), BASE_TAPER)
        assert isinstance(r, str) and r.startswith("unplaced: 1|2"), r


def test_unresolved_or_tautological_between_is_unplaced():
    for src in ("unresolved", "setlist-gap"):
        tracks = mk(["Let It Grow", "tuning", "Scarlet Begonias"], {2: src})
        r = place(tracks, tt_of(("Let It Grow", "1"), ("Scarlet Begonias", "2")))
        assert isinstance(r, str) and "between" in r, r


def test_missing_or_ambiguous_match_is_unplaced():
    r = place(mk(["Bertha", "Scarlet Begonias"]), tt_of(("Let It Grow", "1"), ("Scarlet Begonias", "2")))
    assert isinstance(r, str) and "matches 0 tracks" in r
    r = place(mk(["Let It Grow", "x", "Let It Grow", "Scarlet Begonias"]),
              tt_of(("Let It Grow", "1"), ("Scarlet Begonias", "2")))
    assert isinstance(r, str) and "matches 2 tracks" in r


def test_repeated_title_across_boundary_is_unplaced():
    r = place(mk(["Jam", "Scarlet Begonias"]),
              tt_of(("Jam", "1"), ("Scarlet Begonias", "2"), ("Jam", "2")))
    assert isinstance(r, str) and "other side" in r
    r = place(mk(["Let It Grow", "Jam"]),
              tt_of(("Jam", "1"), ("Let It Grow", "1"), ("Jam", "2")))
    assert isinstance(r, str) and "other side" in r


def test_merged_track_spanning_the_boundary_is_unplaced():
    tracks = mk(["Let It Grow", "Space > Scarlet Begonias"])
    taper = tt_of(("Space", "1"), ("Let It Grow", "1"), ("Scarlet Begonias", "2"))
    r = place(tracks, taper)
    assert isinstance(r, str) and "merged" in r, r


def test_order_must_increase():
    r = place(mk(["Scarlet Begonias", "Let It Grow"]),
              tt_of(("Let It Grow", "1"), ("Scarlet Begonias", "2")))
    assert isinstance(r, str) and "order" in r


def test_tautological_tracks_are_not_evidence():
    tracks = mk(["Let It Grow", "Scarlet Begonias"], {1: "setlist-gap"})
    r = place(tracks, tt_of(("Let It Grow", "1"), ("Scarlet Begonias", "2")))
    assert isinstance(r, str) and "matches 0 tracks" in r


def test_encore_boundary_uses_the_same_test():
    tracks = mk(["Let It Grow", "Scarlet Begonias", "Truckin", "tuning", "Brokedown Palace"])
    taper = tt_of(("Let It Grow", "1"), ("Scarlet Begonias", "2"), ("Truckin", "2"),
                  ("Brokedown Palace", "encore"))
    p = place(tracks, taper)
    assert not isinstance(p, str), p
    assert p.boundaries == (1, 3)
    assert p.sets == ("1", "2", "2", "encore", "encore")


def test_every_boundary_must_place():
    tracks = mk(["A Song", "Donor Rap", "B Song", "C Song"])
    taper = tt_of(("A Song", "1"), ("B Song", "2"), ("C Song", "3"))
    r = place(tracks, taper)
    assert isinstance(r, str) and r.startswith("unplaced: 1|2")
    tracks = mk(["A Song", "B Song", "Donor Rap", "C Song"])
    r = place(tracks, taper)
    assert isinstance(r, str) and r.startswith("unplaced: 2|3")


def test_family_aliases_apply():
    tracks = mk(["Let It Grow", "Scarlet Begonias"])
    taper = tt_of(("Let It Grow", "1"), ("Scarlet", "2"))
    assert isinstance(place(tracks, taper), str)
    assert not isinstance(place(tracks, taper, aliases=GD_SHORTHAND), str)


def test_real_case_declines():
    # moe-1997-02-21: Head and Interstellar Overdrive sit between Moth and the encore.
    tracks = mk(["tuning/banter", "Rebubula", "Spine Of A Dog", "Mexico", "Threw It All Away",
                 "Stranger Than Fiction", "Timmy Tucker", "Brent Black", "Happy Hour Hero",
                 "32 Things", "It", "Moth", "Head", "Interstellar Overdrive", "Head",
                 "tuning/banter", "Spaz Medicine", "Buster", "Seat Of My Pants"])
    d = decide_taper(tracks, {"description": MOE_1997_02_21}, aliases={},
                     today_sets=["1"] * len(tracks))
    assert d.placement is None and d.reason and d.reason.startswith("unplaced: 2|encore")
    assert "between" in d.reason
    # darkstarorchestra-2005-11-16: NFA opens and closes the same stretch (repeated title).
    names = ["Bertha", "Me and My Uncle", "Sugaree", "BIODTL", "Tennessee Jed", "LL Rain",
             "BE Women", "Jack Straw", "Row Jimmy", "WRS Prelude", "WRS Part 1", "Let it Grow",
             "Eyes", "China Doll", "Greatest", "Ramble on", "Big River",
             "Sing Your Blues Away", "China Cat", "I Know You Rider", "El Paso", "He's Gone",
             "Truckin", "NFA", "GDTRFB", "NFA", "Stella Blue", "One More Saturday Night"]
    tracks = mk(names)
    d = decide_taper(tracks, {"description": DSO_2005_11_16}, aliases=GD_SHORTHAND,
                     today_sets=["1"] * len(tracks))
    assert d.placement is None and d.reason and "'NFA'" in d.reason


TWO_SETS = "Set 1: Bertha, Let It Grow\nSet 2: Scarlet Begonias, Truckin\n"


def test_track_title_encore_vetoes():
    tracks = mk(["Bertha", "Let It Grow", "Scarlet Begonias", "Truckin", "Encore: Box Of Rain"])
    d = decide_taper(tracks, {"description": TWO_SETS}, aliases={}, today_sets=["1"] * 5)
    assert d.placement is None and d.reason == "veto: track title"


@pytest.mark.parametrize("text", [
    "Set 1: Bertha, Let It Grow\nSet 2: Scarlet Begonias, Truckin (Encore)\n",
    "Set 1: Bertha, Let It Grow\nSet 2: Scarlet Begonias, Truckin\nencore break\n",
    "Set 1: Bertha, Let It Grow\nSet 2: Scarlet Begonias, Truckin\nE. Box Of Rain\n",
])
def test_encore_like_text_anywhere_vetoes(text):
    tracks = mk(["Bertha", "Let It Grow", "Scarlet Begonias", "Truckin"])
    d = decide_taper(tracks, {"description": text}, aliases={}, today_sets=["1"] * 4)
    assert d.placement is None and d.reason == "veto: encore-like text"


def test_encore_like_does_not_veto_when_an_encore_is_marked():
    text = ("Set 1: Bertha, Let It Grow\nSet 2: Scarlet Begonias, Truckin (Encore)\n"
            "Encore: Brokedown Palace\n")
    tracks = mk(["Bertha", "Let It Grow", "Scarlet Begonias", "Truckin (Encore)",
                 "Encore: Brokedown Palace"])
    d = decide_taper(tracks, {"description": text}, aliases={}, today_sets=["1"] * 5)
    assert d.placement is not None, d.reason
    assert d.placement.sets[-1] == "encore"


def test_decide_taper_reports_source_and_reader_reason():
    tracks = mk(["Bertha", "Let It Grow", "Scarlet Begonias", "Truckin"])
    d = decide_taper(tracks, {"description": "no marks here", "notes": TWO_SETS},
                     aliases={}, today_sets=["1"] * 4)
    assert d.source == "notes" and d.placement is not None and d.reason is None
    d = decide_taper(tracks, {"description": "Set 1: A\nSet 3: B\n"}, aliases={},
                     today_sets=["1"] * 4)
    assert d.placement is None and d.reason.startswith("void:")


# ---------------------------------------------------------------------------------------
# Checkpoint A reader fixes (operator rulings 2026-10-22). Every literal below is copied
# verbatim from `~/.llama/cache/md_<identifier>.json` (named in the comment); the `_TRACKS`
# and `_TODAY` lists are that show's stored `show.json` titles and set labels.
# ---------------------------------------------------------------------------------------

# darkstarorchestra-2013-12-29: md_dso2013-12-29.mk41v.m222.mk5.cmc6.2448.json (description)
DSO_2013_12_29 = (
    'Set 1:\n'
    '01. Intro Set 1\n'
    '02. Bertha\n'
    '03. Jack Straw\n'
    '04. Tennessee Jed\n'
    '05. Looks Like Rain\n'
    '06. Peggy-O\n'
    '07. El Paso\n'
    '08. Friend of the Devil\n'
    '09. Music Never Stopped\n'
    '\n'
    'Set 2:\n'
    '10. Intro Set 2\n'
    '11. Scarlet Begonias>\n'
    '12. Fire on the Mountain>\n'
    "13. Good Lovin'\n"
    '14. Candyman\n'
    '15. Estimated Prophet>\n'
    "16. He's Gone>\n"
    '17. Drums>\n'
    '18. Samson and Delilah\n'
    '19. Terrapin Station>\n'
    '20. Morning Dew>\n'
    '21. Around and Around\n'
    '\n'
    'Encor:\n'
    "22. Uncle John's Band\n"
    '23. U.S. Blues\n'
    '24. Show Reveal - Winterland Ballroom - San Francisco, CA June 7, 1977 \n'
    '25. Mr. Charlie'
)
DSO_2013_12_29_TRACKS = ['Bertha', 'Jack Straw', 'Tennessee Jed', 'Looks Like Rain', 'Peggy-O', 'El Paso', 'Friend of the Devil', 'Music Never Stopped', 'Scarlet Begonias>', 'Fire on the Mountain>', "Good Lovin'", 'Candyman', 'Estimated Prophet>', "He's Gone>", 'Drums>', 'Samson and Delilah', 'Terrapin Station>', 'Morning Dew>', 'Around and Around', "Uncle John's Band", 'U.S. Blues', 'Mr. Charlie']
DSO_2013_12_29_TODAY = ['1', '1', '1', '1', '1', '1', '1', '1', '2', '2', '2', '2', '2', '2', '2', '2', '2', '2', '2', 'encore', 'encore', 'encore']

# railroadearth-2011-10-30: md_rre2011-10-30.flac16.json (description)
RRE_2011_10_30 = (
    'Set I\n'
    '1. Long Way To Go \n'
    '2. Drag Him Down \n'
    '3. Just So You Know \n'
    '4. Lone Croft Farewell \n'
    '5. The Hunting Song \n'
    '6. Pulling the Devil by the Tail \n'
    '7. Mighty River \n'
    '8. 1759 \n'
    '9. Mourning Flies \n'
    '\n'
    ' Set II\n'
    '1. Like a Buddha \n'
    '2. Lordy, Lordy \n'
    '3. Water Fountain Quicksand \n'
    '4. Seven Story Mountain \n'
    '5. Old Man and the Land \n'
    '6. The Forecast \n'
    '7. Warhead Boogie > \n'
    '8. Gallows Pole (A) \n'
    '9E.Wayfaring Stranger'
)
RRE_2011_10_30_TRACKS = ['Long Way To Go', 'Drag Him Down', 'Just So You Know', 'Lone Croft Farewell', 'The Hunting Song', 'Pulling the Devil by the Tail', 'Mighty River', '1759', 'Mourning Flies', 'Like a Buddha', 'Lordy, Lordy', 'Water Fountain Quicksand', 'Seven Story Mountain', 'Old Man and the Land', 'The Forecast', 'Warhead Boogie >', 'Gallows Pole (A)', 'Wayfaring Stranger']
RRE_2011_10_30_TODAY = ['1', '1', '1', '1', '1', '1', '1', '1', '1', '2', '2', '2', '2', '2', '2', '2', '2', 'encore']

# ratdog-2014-02-14: md_rd2014-02-14.mk4.edtyre.json (description)
RATDOG_2014_02_14 = (
    'Set 1\n'
    '\n'
    'The Music Never Stopped >\n'
    'Shakey Ground > \n'
    "Maggie's Farm > \n"
    'Easy Answers\n'
    'Bird Song > \n'
    'Cassidy\n'
    'Weather Report Suite Prelude/Part 1 >  \n'
    'Let It Grow\n'
    '\n'
    'Set 2\n'
    '\n'
    'Friend of the Devil@ > \n'
    'Peggy-O@\n'
    'Looks Like Rain@ \n'
    'Playin in the Band > Eyes of the World > \n'
    'Standing on the Moon > \n'
    'Two Djinn > \n'
    'Not Fade Away\n'
    'E Ripple\n'
    '\n'
    '@ Acoustic'
)
RATDOG_2014_02_14_TRACKS = ['The Music Never Stopped >', 'Shakey Ground >', "Maggie's Farm >", 'Easy Answers', 'Bird Song >', 'Cassidy', 'Weather Report Suite Prelude/Part 1 >', 'Let It Grow', 'Friend of the Devil@ >', 'Peggy-O@', 'Looks Like Rain@', 'Playin in the Band > Eyes of the World >', 'Standing on the Moon >', 'Two Djinn >', 'Not Fade Away', 'Ripple']
RATDOG_2014_02_14_TODAY = ['1', '1', '1', '1', '1', '1', '1', '1', '2', '2', '2', '2', '2', '2', '2', 'encore']

# soundtribesector9-2003-11-01: md_sts9-2003-11-01.json (description)
STS9_2003_11_01 = (
    "Set 1: l1nqs>, Circus, Gobnugget, Surreality, Today, King Pharoh's Tomb, Tricon, Dance\n"
    'Set 2: ISB, ASAA, Grow, Not in our name, Baraka, 4 year puma, Jebez, Just thanks,-e- Freq.1>2'
)
STS9_2003_11_01_TRACKS = ['Circus', 'Gobnugget', 'Surreality', 'Today', "King Pharoh's Tomb", 'Tricon', 'Dance', 'ISB', 'ASAA', 'Grow', 'Not in Our Name', 'Baraka', 'Four Year Puma', 'Jebez', 'Just Thanks', 'Freq 1 > 2']
STS9_2003_11_01_TODAY = ['1', '1', '1', '1', '1', '1', '1', '2', '2', '2', '2', '2', '2', '2', '2', 'encore']

# soundtribesector9-2004-06-25: md_sts9-2004-06-25.json (description)
STS9_2004_06_25 = (
    'Set One: Just Thanks, Posiedon, STS9, Mobsters>Surrealty>EB, Improv F, Baraka\n'
    'Set Two: Tap In, Glogli, What is Love, LSB, Moonsocket, Orbital  E~ Water Song\n'
)
STS9_2004_06_25_TRACKS = ['Poseidon', 'STS9', 'Today', 'Mobsters >', 'Surrealty > EB', 'Improv', 'Baraka', 'Tap In', 'GLOgli', 'What is Love?', "Life's Sweet Breath", 'Moon Socket >', 'Orbital', 'Water Song']
STS9_2004_06_25_TODAY = ['1', '1', '1', '1', '1', '1', '1', '2', '2', '2', '2', '2', '2', 'encore']

# soundtribesector9-2004-10-31: md_sts9-2004-10-31.json (description)
STS9_2004_10_31 = (
    'Set 1*:Intro, Peoples, Arigato, Artifact, 102.4, Since 7th, Providing Sun, Glogli,Bwanf>Sift 5,Forest Hu ,Havona Ascent, Improv,Jebez (v. 2.0)\n'
    '\n'
    'Set 2: Ramone & Emiglio, And Some Are Angels, Inspire Strikes Back, Be Pulse, Orbital, Crystal Instrument, Kamuy, Tap In, E~ Twilight, Really Wut'
)
STS9_2004_10_31_TRACKS = ['Peoples%', 'Arigato', 'Artifact%', '102.4', 'Since 7th', 'Providing Sun', 'Glogli', 'Bwanf>Sift 5', 'Havona Ascent', 'Improv%', 'Jebez (v. 2.0)', 'Ramone & Emiglio', 'And Some Are Angels', 'Inspire Strikes Back', 'Be Pulse', 'Orbital', 'Crystal Instrument', 'Evasive/Kamuy', 'Tap In', 'Twilight', 'Really Wut?', 'Filler-Telefon Tel Aviv***']
STS9_2004_10_31_TODAY = ['1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '2', '2', '2', '2', '2', '2', '2', '2', 'encore', 'encore', 'encore']

# shakedownband-2013-08-24: md_Shakedownband2013-08-24.json (description)
SHAKEDOWN_2013_08_24 = (
    '1st set\n'
    '01. China Cat Sunflower >\n'
    '02. I Know You Rider\n'
    '03. All Over Now\n'
    '04. When Push Comes To Shove\n'
    '05. Cassidy\n'
    '06. CC Rider\n'
    '07. Promised Land\n'
    '08. When I Paint My Masterpiece\n'
    '09. Viola Lee Blues\n'
    '10. Brown Eyed Women\n'
    '2nd Set\n'
    '11. Mississippi Half Step >\n'
    '12. Dark Star Jam >\n'
    '13. Midnight Hour\n'
    '14. Althea\n'
    '15. Help On The Way >\n'
    '16. Slipknot > \n'
    '17. Aiko Aiko\n'
    '18. I Need A Miricle >\n'
    '19. Samson And Delilah\n'
    '20. Loose Lucy >\n'
    '21. Shakedown Street\n'
    '22. Dark Hollow\n'
    '23. Morning Dew\n'
    '24. E Ripple'
)
SHAKEDOWN_2013_08_24_TRACKS = ['China Cat Sunflower >', 'I Know You Rider', 'All Over Now', 'When Push Comes To Shove', 'Cassidy', 'CC Rider', 'Promised Land', 'When I Paint My Masterpiece', 'Viola Lee Blues', 'Brown Eyed Women', 'Mississippi Half Step >', 'Dark Star Jam >', 'Midnight Hour', 'Althea', 'Help On The Way >', 'Slipknot >', 'Aiko Aiko', 'I Need A Miricle >', 'Samson And Delilah', 'Loose Lucy >', 'Shakedown Street', 'Dark Hollow', 'Morning Dew', 'E Ripple']
SHAKEDOWN_2013_08_24_TODAY = ['1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '2', '2', '2', '2', '2', '2', '2', '2', '2', '2', '2', '2', '2', '2']


def _mk_today(titles_: list[str], today: list[str]) -> list[Track]:
    return [Track(index=i + 1, set=s, title=t, filename=f"t{i + 1:02d}.mp3", title_source="tags")
            for i, (t, s) in enumerate(zip(titles_, today))]


# Item 1, the veto gap: each of these encores was written in a form the reader does not
# recognise, and the old veto missed it, so the taper's encore folded into set 2.
VETO_GAP_CASES = {
    "darkstarorchestra-2013-12-29": (DSO_2013_12_29, DSO_2013_12_29_TRACKS, DSO_2013_12_29_TODAY),
    "railroadearth-2011-10-30": (RRE_2011_10_30, RRE_2011_10_30_TRACKS, RRE_2011_10_30_TODAY),
    "ratdog-2014-02-14": (RATDOG_2014_02_14, RATDOG_2014_02_14_TRACKS, RATDOG_2014_02_14_TODAY),
    "soundtribesector9-2003-11-01": (STS9_2003_11_01, STS9_2003_11_01_TRACKS, STS9_2003_11_01_TODAY),
    "soundtribesector9-2004-06-25": (STS9_2004_06_25, STS9_2004_06_25_TRACKS, STS9_2004_06_25_TODAY),
    "soundtribesector9-2004-10-31": (STS9_2004_10_31, STS9_2004_10_31_TRACKS, STS9_2004_10_31_TODAY),
    "shakedownband-2013-08-24": (SHAKEDOWN_2013_08_24, SHAKEDOWN_2013_08_24_TRACKS,
                                 SHAKEDOWN_2013_08_24_TODAY),
}


@pytest.mark.parametrize("slug", sorted(VETO_GAP_CASES))
def test_veto_gap_real_cases_are_not_owned(slug):
    text, names, today = VETO_GAP_CASES[slug]
    tt = read_taper_structure(text)
    assert tt.asserts is True and tt.has_encore is False
    assert tt.encore_like is True
    d = decide_taper(_mk_today(names, today), {"description": text}, aliases=GD_SHORTHAND,
                     today_sets=today)
    assert d.placement is None and d.reason == "veto: encore-like text"


@pytest.mark.parametrize("tail", [
    "Encor:\nRipple\n",             # the `Encor:` typo
    "9E.Ripple\n",                   # E glued to the track number
    "9E)Ripple\n", "9e:Ripple\n",
    "E Ripple\n",                    # E, a space, then the title
    "24. E Ripple\n", "24 E Ripple\n",
    "Tap In, E~ Twilight\n",         # decorated E inside a comma list
    "Orbital  E~ Water Song\n",      # ... or mid-item
    "Just thanks,-e- Freq.1>2\n",
])
def test_encore_like_veto_gap_forms(tail):
    tt = read_taper_structure("Set 1:\nBertha\nSet 2:\nSugaree\n" + tail)
    assert tt.has_encore is False
    assert tt.encore_like is True


def test_encore_like_veto_gap_forms_in_a_marker_lines_songs():
    tt = read_taper_structure("Set 1: Bertha\nSet 2: Sugaree, Tap In, E~ Twilight\n")
    assert tt.has_encore is False and tt.encore_like is True


@pytest.mark.parametrize("tail", [
    "Encorner\n", "Eyes of the World\n", "E-Bow the Letter\n", "Tree~ Hugger\n",
    "Eleanor Rigby\n", "Eel River\n",
])
def test_encore_like_veto_gap_negatives(tail):
    tt = read_taper_structure("Set 1:\nBertha\nSet 2:\nSugaree\n" + tail)
    assert tt.encore_like is False


def test_encore_like_e_space_rule_is_case_sensitive():
    # "e ripple" in lower case is not the `E <Title>` shape.
    tt = read_taper_structure("Set 1:\nBertha\nSet 2:\nSugaree\ne ripple\n")
    assert tt.encore_like is False


# Item 2, a header naming a set and the encore asserts nothing, colon or not: the inline
# split must not turn its `Encore:` into an encore start (cpa-forms' built case).
# perpetualgroove-2006-12-29: md_pgroove2006-12-29.flac16.json (description)
PGROOVE_2006_12_29 = (
    'Disc 1 - Set I\n'
    '\n'
    '1. Sundog\n'
    '2. Space Oddity\n'
    '3. La Casa Bien\n'
    '4. TSMM\n'
    '5. AIM\n'
    '6. Playground\n'
    '\n'
    'Disc 2 - Set II\n'
    '\n'
    '1. Crowded Tub\n'
    '2. Space Paranoids\n'
    '3. Diamonds on the Soles of Her Shoes\n'
    '4. Breeze\n'
    '\n'
    'Disc 3 - Set II cont\n'
    '\n'
    '1. Robot Waltz\n'
    '2. Macumba\n'
    '\n'
    'E:\n'
    '\n'
    "3. Walkin' in Place"
)
PGROOVE_2006_12_29_TRACKS = ['Sundog', 'Space Oddity', 'La Casa Bien', 'TSMM', 'AIM', 'Playground', 'Crowded Tub', 'Space Paranoids', 'Diamonds on the Soles of Her Shoes', 'Breeze', 'Robot Waltz', 'Macumba', "Walkin' in Place"]
PGROOVE_2006_12_29_TODAY = ['1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', 'encore']

PGROOVE_SET_AND_ENCORE = PGROOVE_2006_12_29.replace("Disc 3 - Set II cont", "Disc 3 - Set II + Encore:")


def test_set_and_encore_with_colon_owns_like_the_real_text():
    assert PGROOVE_SET_AND_ENCORE != PGROOVE_2006_12_29
    tracks = _mk_today(PGROOVE_2006_12_29_TRACKS, PGROOVE_2006_12_29_TODAY)
    real = decide_taper(tracks, {"description": PGROOVE_2006_12_29}, aliases={},
                        today_sets=PGROOVE_2006_12_29_TODAY)
    assert real.placement is not None and real.placement.boundaries == (6, 12)
    built = decide_taper(tracks, {"description": PGROOVE_SET_AND_ENCORE}, aliases={},
                         today_sets=PGROOVE_2006_12_29_TODAY)
    assert built.placement == real.placement
    tt = read_taper_structure(PGROOVE_SET_AND_ENCORE)
    assert label(tt, "Robot Waltz") == "2" and label(tt, "Macumba") == "2"
    assert label(tt, "Walkin' in Place") == "encore"


@pytest.mark.parametrize("header", [
    "Set 2 & Encore:", "Set II & Encore:", "Set 2 / Encore:", "Set 2 + Encore:",
    "Set 2 and Encore:", "Disc 3 - Set II + Encore:", "Set 2 & Encore", "Set 2 & Encores:",
])
def test_set_and_encore_header_never_starts_the_encore(header):
    text = f"Set 1:\nBertha\nSet 2:\nSugaree\n{header}\nScarlet Begonias\nE: Ripple\n"
    tt = read_taper_structure(text)
    assert tt.asserts is True and runs(tt) == ["1", "2", "encore"]
    assert label(tt, "Scarlet Begonias") == "2"
    assert label(tt, "Ripple") == "encore"
    # With no later encore marker there is no encore at all: the header names one, so the
    # text is encore-like (the veto's input), and nothing labels a song `encore`.
    tt = read_taper_structure(f"Set 1:\nBertha\nSet 2:\nSugaree\n{header}\nRipple\n")
    assert tt.has_encore is False and tt.encore_like is True
    assert label(tt, "Ripple") == "2"


def test_set_and_encore_header_inline_songs_keep_the_current_set():
    tt = read_taper_structure(
        "Set 1:\nBertha\nSet 2:\nSugaree\nSet 2 & Encore: Scarlet Begonias, E: Ripple\n")
    assert label(tt, "Scarlet Begonias") == "2"
    assert label(tt, "Ripple") == "encore"
    assert "Set 2 &" not in titles(tt) and "Set 2 & Encore:" not in titles(tt)


def test_set_and_encore_three_set_live_shape():
    # "Set 3 / Encore:" (moe2008-01-24's shape): the third set never starts here either.
    tt = read_taper_structure("Set 1:\nBertha\nSet 2:\nSugaree\nSet 3 / Encore:\nRipple\n")
    assert tt.has_encore is False and label(tt, "Ripple") == "2"


def _joined_split(text: str) -> list[str]:
    """`_emit_items`'s inline split over the joined lines (the pre-item-2 `_preprocess`)."""
    import html as _html
    import re as _re
    from llama.setlist import _INLINE_MARKER
    text = _re.sub(r"<br\s*/?>", "\n", text, flags=_re.I)
    text = _html.unescape(_re.sub(r"<[^>]+>", "\n", text))
    raw = [ln.strip() for ln in text.splitlines()]
    return [ln.strip() for ln in _INLINE_MARKER.sub("\n", "\n".join(raw)).splitlines()]


@pytest.mark.parametrize("text", [
    ACOUSTIC_SYNDICATE, GD_1990_03_22, TTB_2019_02_16, DSO_2005_11_16, PAF_2007_10_12,
    # The split's `\s+` may span a line break: "- set 2 -" then a newline splits before
    # "set 2", as in `_emit_items` (ratdog-2007-11-03's shape).
    "Eyes of the World\n     - set 2 - \nPeggy-O\n",
])
def test_preprocess_keeps_the_joined_inline_split(text):
    """(pin) Without a set-and-encore header, `_preprocess` splits exactly as before."""
    from llama.taper import _preprocess
    assert _preprocess(text) == _joined_split(text)


# Item 3, an encore rest of none / no encore / n/a: the taper owns nothing.
# darkstarorchestra-2001-11-09: md_dso2001-11-09.shnf.json (description)
DSO_2001_11_09 = (
    '11/09/01 (Fri) Crystal Ballroom - Portland, OR\n'
    '    Set 1: Cats Under The Stars, Stop That Train, Dear Prudence, Mission In The Rain, I Shall'
    ' Be Released, Sisters And Brothers, Deal\n'
    '\n'
    "    Set 2: Harder They Come, Like A Road, Think, Russian Lullaby, Don't Let Go, Night They"
    ' Drove Old Dixie Down, Midnight Moonlight, E: None Filler: Evangeline, Stir It Up, Breadbox'
    ' > Eleanor Rigby Jam > Breadbox, How Sweet It Is'
)
DSO_2001_11_09_TRACKS = [
    'Cats Under The Stars', 'Stop That Train', 'Dear Prudence', 'Mission in the Rain',
    'I Shall Be Released', 'sisters and Brothers', 'Deal', 'Harder They Come', 'Like A Road',
    'Think', 'Russian Lullaby', "Don't Let Go", 'Night They Drove Old Dixie Down',
    'Midnight Moonlight', 'Evangeline', 'Stir It Up', 'Breadbox>Rigby Jam>Breadbox',
    'How Sweet It Is']
DSO_2001_11_09_TODAY = ['1'] * 7 + ['2'] * 7 + ['3'] * 4


def test_encore_none_real_case_owns_nothing():
    tt = read_taper_structure(DSO_2001_11_09)
    assert tt.asserts is False and tt.reason == "void: encore none"
    d = decide_taper(_mk_today(DSO_2001_11_09_TRACKS, DSO_2001_11_09_TODAY),
                     {"description": DSO_2001_11_09}, aliases=GD_SHORTHAND,
                     today_sets=DSO_2001_11_09_TODAY)
    assert d.placement is None and d.reason == "void: encore none"


def test_encore_none_built_case_owns_nothing():
    # cpa-forms' built case: drop Evangeline from the text and the tape, so the first filler
    # song `Stir It Up` would be read as the encore (fuzzy subphrase on "None Filler: ...").
    text = DSO_2001_11_09.replace("Filler: Evangeline, ", "Filler: ")
    i = DSO_2001_11_09_TRACKS.index("Evangeline")
    names = DSO_2001_11_09_TRACKS[:i] + DSO_2001_11_09_TRACKS[i + 1:]
    today = DSO_2001_11_09_TODAY[:i] + DSO_2001_11_09_TODAY[i + 1:]
    d = decide_taper(_mk_today(names, today), {"description": text}, aliases=GD_SHORTHAND,
                     today_sets=today)
    assert d.placement is None and d.reason == "void: encore none"


@pytest.mark.parametrize("encore", [
    "Encore: none\n", "Encore: None +\n", "ENCORE: NONE\n", "E: N/A\n", "Encore - None\n",
    "Encore: no encore\n", "Encore: No Encores\n", "~Encore~: none\n", "-Encore-\nnone\n",
    "Encore:\nNone\n", "Encore\n(none)\n",
])
def test_encore_none_forms(encore):
    tt = read_taper_structure("Set 1:\nBertha\nSet 2:\nSugaree\n" + encore)
    assert tt.asserts is False and tt.reason == "void: encore none"


@pytest.mark.parametrize("encore", [
    "Encore: Nobody's Fault But Mine\n", "Encore: Nonesuch\n", "Encore: Northern Lights\n",
    "Encore: Not Fade Away\n", "Encore: Ripple, None Shall Pass\n",
])
def test_encore_none_negatives(encore):
    tt = read_taper_structure("Set 1:\nBertha\nSet 2:\nSugaree\n" + encore)
    assert tt.asserts is True and tt.reason is None and tt.has_encore is True


def test_encore_none_collateral_is_accepted():
    # A title starting with the word "None" voids too. It only makes the taper own less.
    tt = read_taper_structure("Set 1:\nBertha\nSet 2:\nSugaree\nEncore: None of Us Are Free\n")
    assert tt.asserts is False and tt.reason == "void: encore none"


# Item 4, reader-local item cleaning (R-ITEM). `parse_setlist` keeps every one of these junk
# items; only the reader cleans them. Real cases: the gate rows cpa-decl measured, each owned
# once its item is clean. Tracks are the adjudication bundle's pre-adjudication table.
# gratefuldead-1980-10-10: md_gd1980-10-10.mtx.chappell.sb03.28740.flac16.json (description)
GD_1980_10_10 = (
    'Set 1: (Acoustic)\n'
    'd1t01 - On The Road Again\n'
    'd1t02 - It Must Have Been The Roses\n'
    'd1t03 - Monkey And The Engineer\n'
    'd1t04 - Jack-a-roe\n'
    'd1t05 - Dark Hollow\n'
    'd1t06 - To Lay Me Down\n'
    'd1t07 - Heaven Help The Fool\n'
    'd1t08 - Bird Song\n'
    'd1t09 - Ripple\n'
    '\n'
    'Set 2: (Electric)\n'
    'd1t10 - Mississippi Half-Step Uptown Toodeloo >\n'
    "d1t11 - Franklin's Tower\n"
    'd1t12 - Me And My Uncle  >\n'
    'd1t13 - Big River\n'
    'd2t01 - Candyman\n'
    'd2t02 - Beat It On Down The Line\n'
    'd2t03 - Row Jimmy\n'
    'd2t04 - New Minglewood Blues\n'
    'd2t05 - Althea\n'
    'd2t06 - Jack Straw\n'
    '\n'
    'Set3:\n'
    'd2t07 - Scarlet Begonias  >\n'
    'd2t08 - Fire On The Mountain\n'
    'd2t09 - Samson And Delilah\n'
    'd2t10 - Big Railroad Blues  \n'
    'd3t01 - Estimated Prophet >\n'
    'd3t02 - Eyes Of The World >\n'
    'd3t03 - Drums >\n'
    'd3t04 - Space >\n'
    "d3t05 - Truckin' >\n"
    "d3t06 - Nobody's Fault jam >\n"
    'd3t07 - Black Peter >\n'
    'd3t08 - Around And Around >\n'
    'd3t09 - The // Promised Land\n'
    '\n'
    'Encore:\n'
    'd3t10 - U.S. Blues'
)
GD_1980_10_10_TRACKS = ['On The Road Again', 'It Must Have Been The Roses', 'Monkey and The Engineer', 'Jack-A-Roe', 'Dark Hollow', 'To Lay Me Down', 'Heaven Help The Fool', 'Bird Song', 'Ripple', 'Mississippi Half-Step Uptown Toodeloo >', "Franklin's Tower", 'Me and My Uncle >', 'Big River', 'Candyman', 'Beat It On Down The Line', 'Row Jimmy', 'New Minglewood Blues', 'Althea', 'Jack Straw', 'Scarlet Begonias >', 'Fire On The Mountain', 'Samson and Delilah', 'Big Railroad Blues', 'Estimated Prophet >', 'Eyes Of The World >', 'Drums >', 'Space >', "Truckin' >", "Nobody's Fault Jam >", 'Black Peter >', 'Around and Around >', 'The // Promised Land', 'U.S. Blues']
GD_1980_10_10_SOURCES = {}
GD_1980_10_10_TODAY = ['1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '2', '2', '2', '2', '2', '2', '2', '2', '2', '2', '2', '2', '2', 'encore']

# railroadearth-2005-08-20: md_rre2005-08-20.schoepsCMC6.flac.json (description)
RRE_2005_08_20 = (
    'Set 1: Disc 1: \n'
    '01. Lordy Lordy \n'
    '02. New Lee Highway Blues> \n'
    '03. Fiddlee \n'
    '04. Chains \n'
    '05. Mourning Flies \n'
    '06. Lois Ann \n'
    '07. Stillwater Getaway \n'
    '08. Wayfaring Stranger \n'
    '09. Waterfountain Quicksand \n'
    '\n'
    'Set 2: Disc 2: \n'
    '01. //Long Way To Go \n'
    '02. Seven Story Mountain \n'
    '03. The Wheel \n'
    '04. Old Man & The Land \n'
    '05. The Hunting Song> \n'
    '06. Black Bear \n'
    '07. Donkey For Sale \n'
    "08. [Timmy's props to the Delaware River Keepers]\n"
    '09. Ragtime Annie Lee \n'
    '\n'
    'Encore: Disc 3: \n'
    '1. Bird In A House \n'
    '2. Railroad Earth'
)
RRE_2005_08_20_TRACKS = ['Lordy Lordy', 'New Lee Highway Blues>', 'Fiddlee', 'Chains', 'Mourning Flies', 'Lois Ann', 'Stillwater Getaway', 'Wayfaring Stranger', 'Waterfountain Quicksand', 'Long Way To Go', 'Seven Story Mountain', 'The Wheel', 'Old Man & The Land', 'The Hunting Song>', 'Black Bear', 'Donkey For Sale', "Timmy's props to the Delaware River Keepers]", 'Ragtime Annie Lee', 'Bird In A House', 'Railroad Earth']
RRE_2005_08_20_SOURCES = {}
RRE_2005_08_20_TODAY = ['1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1']

# greyboyallstars-2012-04-20: md_gba2012-04-20.tlm170.flac16.json (description)
GBA_2012_04_20 = (
    'Set 1\n'
    '1.  tuning / intro\n'
    '2.  The Show Has Begun\n'
    '3.  Profundo Grosso\n'
    "4.  banter - how y'all doin?\n"
    '5.  Fried Grease\n'
    '6.  Hot Dog\n'
    '7.  tuning / thanks\n'
    '8.  Serpico\n'
    '9.  banter - new album\n'
    "10. Breakin' Blood\n"
    '11. The Weasel\n'
    '12. Gravee\n'
    '13. setbreak announce\n'
    '\n'
    'Set 2\n'
    '1.  tuning / banter - Levon Helm condolences\n'
    '2.  The Way You Make Me Feel\n'
    '3.  Hot Pants Breakdown\n'
    '4.  Get A Job\n'
    '5.  Soul Dream\n'
    '6.  Flood In Franklin Park *\n'
    '7.  Inland Emperor\n'
    '8.  Right On -> *+\n'
    '9.  Quantico, VA\n'
    '\n'
    'Set 3\n'
    '1.  tuning\n'
    '2.  V Neck Sweater\n'
    '3.  Taxman\n'
    '4.  Back In The Game\n'
    '5.  Still Waiting\n'
    '6.  Volcanic Acne\n'
    "7.  Wanna Be Startin' Something\n"
    '8.  Confusion\n'
    '9.  banter - one more for you / tuning\n'
    '10. Deck Shoes'
)
GBA_2012_04_20_TRACKS = ['The Show Has Begun', 'Profundo Grosso', 'Fried Grease', 'Hot Dog', 'Serpico', "Breakin' Blood", 'The Weasel', 'Gravee', 'The Way You Make Me Feel', 'Hot Pants Breakdown', 'Get A Job', 'Soul Dream', 'Flood In Franklin Park *', 'Inland Emperor', 'Right On -> *+', 'Quantico, VA', 'V Neck Sweater', 'Taxman', 'Back In The Game', 'Still Waiting', 'Volcanic Acne', "Wanna Be Startin' Something", 'Confusion', 'Deck Shoes']
GBA_2012_04_20_SOURCES = {}
GBA_2012_04_20_TODAY = ['1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '2', '2', '2', '2', '2', '2', '2', '2', '2', '2', '2']

# derektrucksband-2003-12-26: md_dtb2003-12-26.flac16.json (description)
DTB_2003_12_26 = (
    'Disc 1\n'
    'Set I\n'
    '01. Voluntary Slavery\n'
    '02. Gonna Move\n'
    '03. Sahib Teri/Maki Madni\n'
    "04. Preachin' Blues\n"
    '05. For My Brother\n'
    '06. Like Anyone Else\n'
    '07. I Wish I Knew\n'
    "08. Kickin' Bach \n"
    '\n'
    'Disc 2\n'
    'Set II\n'
    '01. Soul Stew\n'
    '02. Everything\n'
    '03. Intro Angola\n'
    '04. Feel So Bad\n'
    '05. 7/4\n'
    "06. Leavin' Trunk\n"
    '\n'
    '\n'
    'Disc 3\n'
    'Set II (Cont.)\n'
    '01. Afro Blue\n'
    "02. Goin' Down Slow\n"
    '03. Joyful Noise\n'
    '\n'
    'Encore:\n'
    '04. 44 Blues\n'
    "05. Freddie's Dead\n"
    '\n'
)
DTB_2003_12_26_TRACKS = ['Voluntary Slavery', 'Gonna Move', 'Sahib Teri/Maki Madni', "Preachin' Blues", 'For My Brother', 'Like Anyone Else', 'I Wish I Knew', "Kickin' Bach", 'Soul Stew', 'Everything', 'Intro Angola', 'Feel So Bad', 'dtb2003-12-26d2t05.mp3', 'Afro Blue', "Goin' Down Slow", 'Joyful Noise', '44 Blues', "Freddie's Dead"]
DTB_2003_12_26_SOURCES = {13: 'unresolved'}
DTB_2003_12_26_TODAY = ['1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', 'encore', 'encore']

# darkstarorchestra-2007-07-06: md_DSO2007-07-06.16b.flac.json (description)
DSO_2007_07_06 = (
    'Dark Star Orchestra\n'
    '07-06-07 \n'
    'Nelson Ledges Quarry Park\n'
    'Nelson twp. OH.\n'
    'Grateful Fest #8 \n'
    "Source: AKG 480's (ck61's) > zaolla cables > V3 > HD-P2 @ 24/96\n"
    'Lineage: cf card > card reader > HDD > cdwav > wavlab downsampled &dithered (UV22HR) 16/44.1 >.flac\n'
    'location: FOB 40~ back 10~ high NOS\n'
    'Taper: Jackoroses\n'
    '\n'
    '\n'
    '\n'
    'Set 1 Disc 1\n'
    '01: Feel Like a Stranger\n'
    '02: Donna intro\n'
    '03: Row Jimmy \n'
    '04: Easywind\n'
    "05: It's all over now\n"
    '06: So Many Roads\n'
    '07: tuning/ stage talk\n'
    '08: Jack Straw\n'
    'Set 2\n'
    '09: US Blues\n'
    '\n'
    'Disc 2\n'
    '01: Estimated Prophet >\n'
    '02: Dark Star >\n'
    '03: Drums >\n'
    '04: Space >\n'
    '05: Throwing Stones > \n'
    '06: Not Fade Away\n'
    '07: Lucy in the Sky with Diamonds\n'
    'E:\n'
    '08: Ripple'
)
DSO_2007_07_06_TRACKS = ['Feel Like a Stranger', 'Row Jimmy', 'Easywind', "It's all over now", 'So Many Roads', 'Jack Straw', 'US Blues', 'Estimated Prophet >', 'Dark Star >', 'Drums >', 'Space >', 'Throwing Stones >', 'Not Fade Away', 'Lucy in the Sky with Diamonds', 'Ripple']
DSO_2007_07_06_SOURCES = {}
DSO_2007_07_06_TODAY = ['1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', 'encore']

# philleshandfriends-2007-10-07: md_plf2007-10-07.mk41.flac16.json (description)
PLF_2007_10_07 = (
    'Set One\n'
    "s1t01: Good Lovin'\n"
    's1t02: Mexican Girl\n'
    's1t03: Candyman\n'
    's1t04: Let It Ride\n'
    's1t05: Sugaree\n'
    's1t06: Casey Jones\n'
    '\n'
    'Set Two\n'
    's2t01: Ripple\n'
    's2t02: Cry Yourself Dry*\n'
    's2t03: Friend of the Devil>\n'
    's2t04: Big Mon* \n'
    's2t05: Brokedown Palace \n'
    '\n'
    'Set Three\n'
    's3t01: The Wheel>\n'
    's3t02: Cryptical Envelopment>\n'
    's3t03: All Along The Watchtower>\n'
    's3t04: The Other One\n'
    's3t05: Help on The Way>\n'
    's3t06: Slipknot!>\n'
    "s3t07: Franklin's Tower\n"
    's3t08: Turn On Your Lovelight\n'
    's3t09: crowd/donor rap/intros\n'
    'encore\n'
    's3t10:  Not Fade Away'
)
PLF_2007_10_07_TRACKS = ["Good Lovin'", 'Mexican Girl', 'Candyman', 'Let It Ride', 'Sugaree', 'Casey Jones', 'Ripple', 'Cry Yourself Dry*', 'Friend of the Devil>', 'Big Mon*', 'Brokedown Palace', 'The Wheel>', 'Cryptical Envelopment>', 'All Along The Watchtower>', 'The Other One', 'Help on The Way>', 'Slipknot!>', "Franklin's Tower", 'Turn On Your Lovelight', 'crowd/donor rap/intros', 'Not Fade Away']
PLF_2007_10_07_SOURCES = {}
PLF_2007_10_07_TODAY = ['1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', 'encore', 'encore']

# railroadearth-2014-11-28: md_rre2014-11-28.spc4.hypers.flac16.json (description)
RRE_2014_11_28 = (
    "Horn O'Plenty 2014 Night 1\n"
    'Set 1\n'
    "01 Won't You Come And Sing For Me\n"
    '02 The Jupiter And The 119\n'
    '03 Happy Song\n'
    '04 Saddle Of The Sun\n'
    '05 Grandfather Mountain (A)\n'
    '06 Flower Between The Stones (A)\n'
    '07 Mission Man (B)\n'
    '08 Hangtown Ball (A)\n'
    '\n'
    'Set 2\n'
    '01 Lordy, Lordy\n'
    '02 The Good Life\n'
    '03 Donkey For Sale\n'
    "04 Potter's Field\n"
    '05 Bread And Water\n'
    '06 Black Elk Speaks ->\n'
    '07 Tuba Mirum -> (A)\n'
    '08 Face With A Hole (A)\n'
    '09 Monkey (A)\n'
    '10 Like A Buddha (A)\n'
    '11 Give That Boy A Hand\n'
    '12 One More Night On The Road (A)\n'
    '13 Take A Bow (A)\n'
    '14 crowd\n'
    'Encore\n'
    '15 Roadhouse Blues (A)\n'
    '\n'
    "Bill Evans' Soulgrass opened the show.\n"
    '\n'
    'Show notes\n'
    '\n'
    '(A) with the "Stroudsburg Horn Men":\n'
    'Jay Rattman -- alto Sax and clarinet \n'
    'Jim Daniels -- bass trombone and tuba \n'
    'Tom Hamilton -- tenor and baritone Sax, carinet \n'
    'Sean McNally -- trumpet and flugelhorn \n'
    'Arrangements by Jay Rattman\n'
    '\n'
    '(B) with Bill Evans on tenor Sax'
)
RRE_2014_11_28_TRACKS = ["Won't You Come And Sing For Me", 'The Jupiter And The 119', 'Happy Song', 'Saddle Of The Sun', 'Grandfather Mountain (A)', 'Flower Between The Stones (A)', 'Mission Man (B)', 'Hangtown Ball (A)', 'Lordy, Lordy', 'The Good Life', 'Donkey For Sale', "Potter's Field", 'Bread And Water', 'Black Elk Speaks ->', 'Tuba Mirum -> (A)', 'Face With A Hole (A)', 'Monkey (A)', 'Like A Buddha (A)', 'Give That Boy A Hand', 'One More Night On The Road (A)', 'Take A Bow (A)', 'crowd', 'Roadhouse Blues (A)']
RRE_2014_11_28_SOURCES = {}
RRE_2014_11_28_TODAY = ['1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', 'encore']

# robertwalters20thcongress-2004-01-02: md_RWTC04-01-02.shnf.json (description)
RWTC_2004_01_02 = (
    'Set 1-Disk 1 \n'
    '1. Bygones Be\n'
    '2. Aquafresh\n'
    '3. Circle Limit\n'
    "4. Corry's Snail and Slug Death\n"
    '5. Rack and Pinion\n'
    '6. Greyboy\n'
    '7. Nautilus->\n'
    '8. Rapture (blondie)->\n'
    '9. Nautilus\n'
    '10.Freshman 10 \n'
    '\n'
    'Set 2:-Disk 2 \n'
    '1. El Cuervo \n'
    '2. 2% Body Fat\n'
    '3. Shemp Time\n'
    '4. X->\n'
    '5. Planet of the Superkids\n'
    '6. Be Yourself\n'
    '==Encores==\n'
    '7. Instant Karma\n'
    '8. Instant Death'
)
RWTC_2004_01_02_TRACKS = ['Bygones Be', 'Aquafresh', 'Circle Limit', "Corry's Snail and Slug Death", 'Rack and Pinion', 'Greyboy', 'Nautilus >', 'Nautilus', 'Freshman 10 (Pete McNeil on Drums)', 'El Cuervo (Live Debut)', '2% Body Fat', 'Shemp Time', 'RWTC04-01-02d2.shnf/RW2C04-01-02d2t04.mp3', 'Planet of the Superkids', 'Be Yourself', 'Instant Karma', 'Instant Death']
RWTC_2004_01_02_SOURCES = {13: 'unresolved'}
RWTC_2004_01_02_TODAY = ['1', '1', '1', '1', '1', '1', '1', '1', '1', '2', '2', '2', '2', '2', '2', '2', '2']

# infamousstringdusters-2008-12-06: md_is2008-12-06.flac16.aud.json (description), excerpt
ISD_2008_12_06 = (
    "Set 1\n=====\n1. Intro / Tuning\n2. Three Days In July\n3. 40 West\n"
    "4. Won't Be Coming Back\n5. Let's Rekindle Our Love\n6. Tuning / Banter\n"
    "7. Bound for Tennessee\n8. Tuning / Banter\n9. Gettin' Down the Road\n10. Cluck Ol' Hen\n"
    "11. Tuning / Banter\n12. Fork In The Road\n13. Tuning / Banter\n14. My Destination\n\n"
    "Set 2\n=====\n1. Intro / Tuning\n2. You Can't Handle the Truth\n"
    "3. When Silence is the Only Sound\n4. Tuning / Banter\n5. High on a Mountain Top\n"
    "6. I Ain't Been Myself in Years\n7. Tuning\n8. Black Rock\n9. Tuning / Banter\n10.\n"
    "11. Deep Elem Blues\n12. Dream You Back\n13. Tuning / Banter\n14. Get It While You Can\n"
    "15. Tuning / Banter\n16. Lovin' You\n17. Intros / Crowd\n18. Sunny Side Of The Mountain\n"
    "\nEncores\n=======\n19. Callback / Banter\n20. Poor Boy's Delight\n21. Tuning / Banter\n"
    "22. \n\n"
)


def _mk_src(titles_: list[str], today: list[str], sources: dict[int, str]) -> list[Track]:
    return [Track(index=i + 1, set=s, title=t, filename=f"t{i + 1:02d}.mp3",
                  title_source=sources.get(i + 1, "tags"))
            for i, (t, s) in enumerate(zip(titles_, today))]


R_ITEM_CASES = {
    # slug: (text, tracks, sources, today, family, expected boundaries)
    "gratefuldead-1980-10-10": (GD_1980_10_10, GD_1980_10_10_TRACKS, GD_1980_10_10_SOURCES,
                                GD_1980_10_10_TODAY, True),
    "railroadearth-2005-08-20": (RRE_2005_08_20, RRE_2005_08_20_TRACKS, RRE_2005_08_20_SOURCES,
                                 RRE_2005_08_20_TODAY, False),
    "greyboyallstars-2012-04-20": (GBA_2012_04_20, GBA_2012_04_20_TRACKS, GBA_2012_04_20_SOURCES,
                                   GBA_2012_04_20_TODAY, False),
    "derektrucksband-2003-12-26": (DTB_2003_12_26, DTB_2003_12_26_TRACKS, DTB_2003_12_26_SOURCES,
                                   DTB_2003_12_26_TODAY, False),
    "darkstarorchestra-2007-07-06": (DSO_2007_07_06, DSO_2007_07_06_TRACKS,
                                     DSO_2007_07_06_SOURCES, DSO_2007_07_06_TODAY, True),
    "philleshandfriends-2007-10-07": (PLF_2007_10_07, PLF_2007_10_07_TRACKS,
                                      PLF_2007_10_07_SOURCES, PLF_2007_10_07_TODAY, True),
    "railroadearth-2014-11-28": (RRE_2014_11_28, RRE_2014_11_28_TRACKS, RRE_2014_11_28_SOURCES,
                                 RRE_2014_11_28_TODAY, False),
    "robertwalters20thcongress-2004-01-02": (RWTC_2004_01_02, RWTC_2004_01_02_TRACKS,
                                             RWTC_2004_01_02_SOURCES, RWTC_2004_01_02_TODAY, False),
}


@pytest.mark.parametrize("slug", sorted(R_ITEM_CASES))
def test_r_item_real_cases_own_once_their_items_are_clean(slug):
    text, names, sources, today, family = R_ITEM_CASES[slug]
    d = decide_taper(_mk_src(names, today, sources), {"description": text},
                     aliases=GD_SHORTHAND if family else {}, today_sets=today)
    assert d.placement is not None, d.reason


def test_r_item_real_case_titles():
    # `s2t01: Ripple` (filename-token prefix)
    assert label(read_taper_structure(PLF_2007_10_07), "Ripple") == "2"
    # `Set 2: (Electric)`: a parenthetical alone in a header line's rest is no item
    tt = read_taper_structure(GD_1980_10_10)
    assert "(Electric)" not in titles(tt) and "(Acoustic)" not in titles(tt)
    assert tt.items[0].title == "On The Road Again"
    # `=====` underlines are no items
    tt = read_taper_structure(ISD_2008_12_06)
    assert not any(set(t) <= set("=") for t in titles(tt))
    assert tt.items[0].title == "Three Days In July"
    # `Set 2: Disc 2:` / `Encore: Disc 3:` / `Set 2:-Disk 2`: a disc label in a header's rest
    tt = read_taper_structure(RRE_2005_08_20)
    assert not any(t.lower().startswith("disc") for t in titles(tt))
    assert label(tt, "//Long Way To Go") == "2"
    tt = read_taper_structure(RWTC_2004_01_02)
    assert "-Disk 2" not in titles(tt) and label(tt, "El Cuervo") == "2"
    # `04. 44 Blues`: one prefix strip, never two
    assert label(read_taper_structure(DTB_2003_12_26), "44 Blues") == "encore"
    # `08: Ripple` (an `NN:` prefix)
    assert label(read_taper_structure(DSO_2007_07_06), "Ripple") == "encore"
    # `9.  Quantico, VA` / `01 Lordy, Lordy`: one numbered title is not split on its comma
    assert label(read_taper_structure(GBA_2012_04_20), "Quantico, VA") == "2"
    assert label(read_taper_structure(RRE_2014_11_28), "Lordy, Lordy") == "2"


def test_parse_setlist_keeps_the_junk_items():
    """(pin) The cleaning is the reader's alone: `parse_setlist` still yields the junk."""
    parsed = [i.title for i in parse_setlist(GD_1980_10_10).items]
    assert "(Electric)" in parsed
    parsed = [i.title for i in parse_setlist(GBA_2012_04_20).items]
    assert "Quantico" in parsed and "VA" in parsed
    parsed = [i.title for i in parse_setlist(DTB_2003_12_26).items]
    assert "Blues" in parsed and "44 Blues" not in parsed


@pytest.mark.parametrize("line, kept", [
    ("=====", None), ("-", None), ("~~~ ***", None), ("%", None), ("Sugaree, *#", "Sugaree"),
    ("?", "?"),  # an unknown song is not decoration
    ("Jam", "Jam"),
])
def test_decoration_only_items_are_dropped(line, kept):
    tt = read_taper_structure(f"Set 1:\nBertha\n{line}\nSet 2:\nSugaree\n")
    assert titles(tt) == ["Bertha"] + ([kept] if kept else []) + ["Sugaree"]


@pytest.mark.parametrize("rest, kept", [
    ("(Electric)", []), ("[Acoustic]", []), ("Disc 2:", []), ("-Disk 2", []), ("CD 2", []),
    ("Disc Two", []),
    ("(I Can't Get No) Satisfaction", ["(I Can't Get No) Satisfaction"]),
    ("Discotheque", ["Discotheque"]), ("Disc Jockey Blues", ["Disc Jockey Blues"]),
])
def test_header_rest_parenthetical_and_disc_label_items_are_dropped(rest, kept):
    tt = read_taper_structure(f"Set 1:\nBertha\nSet 2: {rest}\nSugaree\n")
    assert titles(tt) == ["Bertha"] + kept + ["Sugaree"]


def test_parenthetical_song_line_is_kept_outside_a_header_rest():
    # Only a header line's rest drops a lone parenthetical: an own-line one stays an item.
    tt = read_taper_structure("Set 1:\nBertha\n(Electric)\nSet 2:\nSugaree\n")
    assert label(tt, "(Electric)") == "1"


@pytest.mark.parametrize("line, title", [
    ("s2t01: Ripple", "Ripple"), ("s3t10:  Not Fade Away", "Not Fade Away"),
    ("S1T02 Bertha", "Bertha"),
    ("08: Ripple", "Ripple"), ("8: Ripple", "Ripple"),
    ("12:Bars", "12:Bars"),  # `NN:` needs a following space
    ("Sts9 Jam", "Sts9 Jam"),
])
def test_track_token_and_colon_prefixes_are_stripped(line, title):
    tt = read_taper_structure(f"Set 1:\nBertha\nSet 2:\n{line}\n")
    assert titles(tt) == ["Bertha", title]


def test_one_prefix_strip_only():
    text = "Set 1:\n01. Bertha\n02. 44 Blues\n03. 08 Days\nSet 2:\n04. 17 Cents\n05. Ripple\n"
    assert titles(read_taper_structure(text)) == ["Bertha", "44 Blues", "08 Days", "17 Cents",
                                                  "Ripple"]
    # An unpunctuated track number on an enumerated text is still stripped once.
    text = "Set 1:\n01 Bertha\n02 100 Years\nSet 2:\n03 Sugaree\n"
    assert titles(read_taper_structure(text)) == ["Bertha", "100 Years", "Sugaree"]
    # The `\d{1,3}` bound holds: no new strip reaches into a digit-leading title.
    text = "Set 1:\nBertha\n08 Days\n1952 Vincent Black Lightning\nSet 2:\nSugaree\n"
    assert titles(read_taper_structure(text)) == ["Bertha", "08 Days",
                                                  "1952 Vincent Black Lightning", "Sugaree"]


def test_numbered_title_comma_kept_only_on_enumerated_text():
    text = "Set 1:\n1. Bertha\n2. Quantico, VA\n3. Sugaree\nSet 2:\n4. Lordy, Lordy\n5. Ripple\n"
    assert titles(read_taper_structure(text)) == ["Bertha", "Quantico, VA", "Sugaree",
                                                  "Lordy, Lordy", "Ripple"]
    # A comma before a footnote mark or a duration still splits (Mark Burgin's
    # `02 Casualty,*` / `10  ??Instrumental,  [2:31]`, yondermountainstringband-2008-07-19,
    # larrykeel-2009-12-02), and so does a trailing one.
    text = "Set 1:\n01 Intro,\n02 Casualty,*\n03 Up on the Hill, %\nSet 2:\n04 Ripple,  [2:31]\n"
    assert titles(read_taper_structure(text)) == ["Casualty", "Up on the Hill", "Ripple"]
    # A segue still splits a numbered line.
    text = "Set 1:\n1. Bertha\n2. Scarlet Begonias > Fire On The Mountain\n3. Sugaree\nSet 2:\n4. Ripple\n"
    assert titles(read_taper_structure(text))[1:3] == ["Scarlet Begonias", "Fire On The Mountain"]
    # Not enumerated, or an unnumbered line: commas split as before.
    assert titles(read_taper_structure("Set 1: Bertha, Sugaree\nSet 2: Ripple, Truckin\n")) == [
        "Bertha", "Sugaree", "Ripple", "Truckin"]
    text = "Set 1:\n1. Bertha\n2. Sugaree\n3. Jack Straw\nSet 2:\nRipple, Truckin\n"
    assert titles(read_taper_structure(text))[-2:] == ["Ripple", "Truckin"]


# Item 5, ruling (b): a recognised numbered header followed directly by a (duration), a
# (time range) or `...` is still that header.
# cowboyjunkies-2012-04-26: md_cowboyjunkies2012-04-26.at822.flac16.json (description)
CJ_2012_04_26 = (
    '*** 16bit regular CD version ***\n'
    '\n'
    'SET ONE (50:28)\n'
    '\n'
    '01. Sing In My Meadow\n'
    '02. Wrong Piano\n'
    '03. West Of Rome\n'
    '04. Third Crusade\n'
    '05. I Cannot Sit Sadly By Your Side\n'
    '06. Stranger Here\n'
    '07. Damaged From The Start\n'
    '08. Fairytale\n'
    '09. Unanswered Letter\n'
    '\n'
    'SET TWO (1:15:03)\n'
    '\n'
    '01. Sweet Jane\n'
    '02. Dreaming My Dreams With You\n'
    '03. A Common Disaster\n'
    '04. 32-20 Blues\n'
    '05. Five Room Love Story\n'
    '06. A Horse In The Country\n'
    "07. Bea's Song\n"
    '08. Murder, Tonight, In The Trailer Park >\n'
    '09. Those Final Feet\n'
    '10. (Band Introductions)\n'
    '11. Misguided Angel\n'
    '\n'
    'ENCORE\n'
    '\n'
    '12. Powderfinger\n'
    '13. Fuck, I Hate The Cold'
)
CJ_2012_04_26_TRACKS = ['Sing In My Meadow', 'Wrong Piano', 'West Of Rome', 'Third Crusade', 'I Cannot Sit Sadly By Your Side', 'Stranger Here', 'Damaged From The Start', 'Fairytale', 'Unanswered Letter', 'Sweet Jane', 'Dreaming My Dreams With You', 'A Common Disaster', '32-20 Blues', 'Five Room Love Story', 'A Horse In The Country', "Bea's Song", 'Murder, Tonight, In The Trailer Park >', 'Those Final Feet', '(Band Introductions)', 'Misguided Angel', 'Powderfinger', 'Fuck, I Hate The Cold']
CJ_2012_04_26_SOURCES = {}
CJ_2012_04_26_TODAY = ['1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', 'encore', 'encore']

# joerussosalmostdead-2018-02-15: md_jrad2018-02-15.cmc621.cmc64.sbd.matrix.flac16.json (notes)
JRAD_2018_02_15 = (
    "Joe Russo's Almost Dead 02/15/2018 War Memorial Auditorium, Nashville, TN\n"
    '\n'
    "Source 1: Schoeps cmc621 (On Stage, Split 25') -> Avid SC-48 -> Zoom H6N -> WAV (@24/96);\n"
    'Source 2: Schoeps cmc64 (FOH booth) -> ART Tube MP Studio Pre Amps -> Zoom H6N -> WAV (@24/96);\n'
    'Source 3: SBD (Avid SC-48) -> Zoom H6N -> WAV (@24/96);\n'
    '\n'
    'Transfer: WAVs -> SoundForge Pro 11.0 (Time Align, normalize) -> Vegas Pro 13.0 (mix/render) -> SoundForge Pro 11.0 (EQ, normalize, fades, 96->44.1 iZotope 64-Bit SRC; 24->16 bit iZotope MBIT+ Dither) -> CDWav -> FLAC\n'
    '\n'
    'Costello & McRoberts Ultra Mix - Recording and FOH mix by Peter Costello - Monitors by Aaron Gittleman - Audio edited, mixed and mastered by Eric McRoberts 07/01-03/2018\n'
    '\n'
    '\tSet One (8:20PM - 9:45PM):\n'
    '01.  Jam @@ ->\n'
    '02.  Cassidy ## ->\n'
    '03.  Here Comes Sunshine @ ->\n'
    '04.  Not Fade Away # ->\n'
    '05.  Ruben & Cherise $ ->\n'
    '06.  Doin That Rag % (NA)\n'
    '07.  Magnificent Sanctuary Band ^\n'
    '\n'
    '\tSet Two (10:16PM - 11:53PM):\n'
    '01.  Eyes Of The World & ->\n'
    '02.  The Eleven * ->\n'
    '03.  Feel Like A Stranger ->\n'
    '04.  China Cat Sunflower ->\n'
    '05.  I Know You Rider >\n'
    '06.  The Other One\n'
    '\tEncore:\n'
    '07.  Shakedown Street\n'
    '\n'
    '@@ - With GDTRFB teases (Band)\n'
    '## - With New Speedway Boogie Teases (Band)\n'
    '@ - With a “Fearless” (Pink Floyd) Tease (MB)\n'
    '# - With an “I Want Candy” (Bow Wow Wow) Jam, A “Simpsons Theme” (Danny Elfman) Tease (SM) & Throwin Stones Teases (Band)\n'
    '$ - With a Terrapin Station Tease (Band) & maybe something else?\n'
    '% - First time played by Almost Dead since 2016-01-10, Capitol Theatre, Port Chester, NY, a gap of 79 shows. NA is Nicole Atkins on Lead Vocals.\n'
    '^ - First time played by Almost Dead since 2016-10-08, Brooklyn Bowl, Brooklyn, NY, a gap of 55 shows. (It was played at the Tiger Auction Benefit last May - not a JRAD Show.)\n'
    '& - With a DD bass solo & the “1973 Ending” changes\n'
    '* - With a “Duo Jam”\n'
    '+ - With a “Fly Like an Eagle” (Steve Miller) Tease (MB), maybe an “Axel F Theme” (Herbie Hancock) Tease (SM) & unknown teases from (MB & SM) that I’ll update if I figure out.\n'
    '\n'
    'Pre Show / Set Break Music: Costello’s Motown Mix\n'
    "Post Show Walk Out Music: Stayin' Alive, The Bee Gees\n"
    'Poster: New Antlers\n'
    '\n'
    'Joe Russo - Drums, Vocals\n'
    'Tom Hamilton - Guitar, Vocals\n'
    'Scott Metzger - Guitar, Vocals\n'
    'Marco Benevento - Keyboards, Vocals\n'
    'Dave Dreiwitz - Bass, Vocals\n'
    '\n'
    'Show #139\n'
    '\n'
    'There is a higher quality 24 bit version of this recording available here: <a href="https://archive.org/details/jrad2018-02-15.cmc621.cmc64.sbd.matrix.flac24" rel="nofollow">https://archive.org/details/jrad2018-02-15.cmc621.cmc64.sbd.matrix.flac24</a>'
)
JRAD_2018_02_15_TRACKS = ['Jam @@ ->', 'Cassidy ## ->', 'Here Come Sunshine @ ->', 'Not Fade Away # ->', 'Ruben & Cherise $ ->', 'Doin That Rag % (NA)', 'Magnificent Sanctuary Band ^', 'Eyes Of The World & ->', 'The Eleven * ->', 'Feel Like A Stranger ->', 'China Cat Sunflower ->', 'I Know You Rider >', 'The Other One', 'Shakedown Street']
JRAD_2018_02_15_SOURCES = {}
JRAD_2018_02_15_TODAY = ['1', '1', '1', '1', '1', '1', '1', '2', '2', '2', '2', '2', '2', '3']

# joerussosalmostdead-2017-03-11: md_jrad2017-03-11.cmc621.cmc641vxt.sbd.matrix.flac16.json (notes)
JRAD_2017_03_11 = (
    "Joe Russo's Almost Dead 03/11/2017 Brooklyn Bowl, Brooklyn, NY\n"
    '\n'
    "Source 1: Schoeps cmc621 (On Stage, Split 20') -> Sonosax SX-M2 -> Sound Devices 788T -> WAV (@24/96);\n"
    'Source 2: Schoeps cmc641v xt (PAS in FOH booth) -> Sonosax SX-M2 -> Sound Devices 788T -> WAV (@24/96);\n'
    'Source 3: SBD (Digidesign/Avid Profile) -> Sound Devices 788T -> WAV (@24/96);\n'
    '\n'
    'Transfer: WAVs -> SoundForge Pro 11.0 (EQ, Time Align, normalize) -> Vegas Pro 13.0 (mix/render) -> SoundForge Pro 11.0 (EQ, normalize, fades, 96->44.1 iZotope 64-Bit SRC; 24->16 bit iZotope MBIT+ Dither) -> CDWav -> FLAC\n'
    '\n'
    'Costello & McRoberts Ultra Mix - Recorded by Peter Costello & Eric McRoberts - FOH mix by Peter Costello - Monitors by Aaron Gittleman - Lights by Jason Liggy Liggett - Video by Sean Smith - Edited, mixed and mastered by Eric McRoberts 03/12/2017\n'
    '\n'
    '\tSet One (9:30PM - 10:46PM):\n'
    '01.  Jam @ ->\n'
    '02.  Cassidy # (SM) ->\n'
    '03.  Let It Grow Jam ->\n'
    '04.  Born Cross Eyed Jam $ ->\n'
    '05.  Tennessee Jed % (TH) ->\n'
    '06.  Jam %% ->\n'
    '07.  Chuckles ^ ->\n'
    '08.  Tequila & ->\n'
    '09.  Chuckles Reprise ^ ->\n'
    '10.  Big River (SM) >\n'
    '11.  Box Of Rain (JR)\n'
    '12.  Althea (TH) * >\n'
    '13.  Throwing Stones (SM)\n'
    '\n'
    '\tSet Two (11:18PM - 12:41AM):\n'
    '01.  Deal (TH) >\n'
    '02.  Good Lovin + (SM) ->\n'
    '03.  Summer Nights Jam @@ ->\n'
    '04.  Good Lovin’ Reprise (SM) ->\n'
    '05.  Heartbreaker Jam ## ->\n'
    '06.  Cumberland Blues $$ (All) ->\n'
    '07.  Terrapin Station (TH) ->\n'
    '08.  The Other One Jam ->\n'
    '09.  Terrapin Suite (TH/JR) ^^\n'
    '\tEncore: \n'
    '10.  One More Saturday Night (SM)\n'
    '\n'
    '@ - With a China>Rider Transition Jam Tease (TH)\n'
    '# - Unfinished\n'
    '$ - With “Rainy Day Women #12 & 35” (Bob Dylan) Teases (Band)\n'
    '% - With a Spoonful Tease (SM) & a lengthy Marco Solo that included “Chopsticks”\n'
    '%% - With “Big River” teases\n'
    '^ - WOLF!! Original, First Time Played By Almost Dead\n'
    '& - The Champs Original, First Time Played By Almost Dead\n'
    '* - With a “So What” (Miles Davis) Tease (SM) & a full band “All of my Love” (Led Zeppelin) Jam\n'
    '+ - With a back & forth between Marco & Scott that teased numerous jazz standards including “St. Thomas” (Sonny Rollins) & “Four” (Miles Davis)\n'
    '@@ - Olivia Newton-John & John Travolta / Grease Soundtrack Original, (AKA Summer Lovin’ - written by Jim Jacobs and Warren Casey). First Time Played By Almost Dead\n'
    '## - Led Zeppelin Original, First Time Played By Almost Dead\n'
    '$$ - With a “Heartbreaker” (Led Zeppelin) Tease (DD) & a Slipknot! Jam (Band)\n'
    '^^ - This is probably the 1st "split" Terrapin Suite, making me think that I should reassess how I note the full version of the song, vs. when they just play the first part that the GD usually played live...\n'
    '\n'
    'Joe Russo - Drums, Vocals\n'
    'Tom Hamilton - Guitar, Vocals\n'
    'Scott Metzger - Guitar, Vocals\n'
    'Marco Benevento - Keyboards, Vocals\n'
    'Dave Dreiwitz - Bass\n'
    '\n'
    'Show #102- SOLD OUT ~ THANK YOU!!!  Pre Show Music DJ Uncle Mike from Doors until 8:30PM.  Kevin Kendrick DJ’d before, between sets & after.\n'
    '\n'
    'There is a higher quality 24 bit version of this recording available here:  <a href="https://archive.org/details/jrad2017-03-11.cmc621.cmc641vxt.sbd.matrix.flac24" rel="nofollow">https://archive.org/details/jrad2017-03-11.cmc621.cmc641vxt.sbd.matrix.flac24</a>'
)
JRAD_2017_03_11_TRACKS = ['Jam @ ->', 'Cassidy # (SM) ->', 'Let It Grow Jam ->', 'Tennessee Jed % (TH) ->', 'Jam %% ->', 'Big River (SM) >', 'Box Of Rain (JR)', 'Althea (TH) * >', 'Throwing Stones (SM)', 'Deal (TH) >', 'Good Lovin + (SM) ->', 'Good Lovin’ Reprise (SM) ->', 'Heartbreaker Jam ## ->', 'Cumberland Blues $$ (All) ->', 'Terrapin Station (TH) ->', 'The Other One Jam ->', 'Terrapin Suite (TH/JR) ^^', 'One More Saturday Night (SM)']
JRAD_2017_03_11_SOURCES = {}
JRAD_2017_03_11_TODAY = ['1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '2', '2', '2', '2', '2', '2', '2', 'encore']


ANNOTATED_CASES = {
    "cowboyjunkies-2012-04-26": (CJ_2012_04_26, CJ_2012_04_26_TRACKS, CJ_2012_04_26_TODAY,
                                 "description"),
    "joerussosalmostdead-2018-02-15": (JRAD_2018_02_15, JRAD_2018_02_15_TRACKS,
                                       JRAD_2018_02_15_TODAY, "notes"),
    "joerussosalmostdead-2017-03-11": (JRAD_2017_03_11, JRAD_2017_03_11_TRACKS,
                                       JRAD_2017_03_11_TODAY, "notes"),
}


@pytest.mark.parametrize("slug", sorted(ANNOTATED_CASES))
def test_annotated_header_real_cases_own(slug):
    text, names, today, field = ANNOTATED_CASES[slug]
    d = decide_taper(_mk_today(names, today), {field: text}, aliases={}, today_sets=today)
    assert d.placement is not None, d.reason
    assert d.source == field


@pytest.mark.parametrize("h1, h2", [
    ("SET ONE (50:28)", "SET TWO (1:15:03)"),
    ("Set One (9:30PM - 10:46PM):", "Set Two  (11:18PM - 12:41AM):"),
    ("Set One (8:38PM - 9:56PM):", "Set Two (10:26PM - 12:14AM?):"),
    ("Set I (66:41)", "Set II (61:20)"),
    ("Disc 1 - Set 1 (61:20):", "Disc 2 - Set 2 (58:02):"),
    ("Disc 1 (Set 1) (45:10)", "Disc 2 (Set 2) (50:00)"),
    ("Set 1 (9:30 pm - 10:46 pm)", "Set 2 (1:02:03.5)"),
])
def test_annotated_headers_are_headers(h1, h2):
    tt = read_taper_structure(f"{h1}\nBertha\nSugaree\n{h2}\nScarlet Begonias\nRipple\n")
    assert tt.asserts is True and runs(tt) == ["1", "2"], tt.reason
    assert titles(tt) == ["Bertha", "Sugaree", "Scarlet Begonias", "Ripple"]


@pytest.mark.parametrize("line", [
    "Set 1 (Acoustic)",               # a word, not a duration or time
    "Set 1 (night)",
    "Set 1 @ (8:16PM - 9:18PM):",     # the annotation must directly follow the header token
    "Set 1 (50:28) Bertha",           # songs after an annotation need `:` or `-`
    "Set 1 (50:28 w/ Bill Evans)",
])
def test_annotation_forms_that_stay_unrecognised(line):
    tt = read_taper_structure(f"{line}\nSugaree\nSet 2:\nRipple\n")
    assert line in titles(tt) or any(t.startswith(line.split(" (")[0] + " (") for t in titles(tt))
    assert label(tt, "Sugaree") == "1" and label(tt, "Ripple") == "2"


# Item 6, ruling (c): the disc-and-set shapes. Each carries `Set` or an ordinal set and reads
# as set M.
# ratdog-2008-11-16: md_rd2008-11-16.mg210.flac16.json (description)
RATDOG_2008_11_16 = (
    'Set I Disc 1: 74:16\n'
    '\n'
    '01. Milestones Jam* >\n'
    '02. Here Comes Sunshine > \n'
    '03. Mama Tried\n'
    "04. It's All Over Now, Baby Blue\n"
    '05. Mission in the Rain\n'
    '06. Lucky Enough >\n'
    '07. Big Boss Man\n'
    '08. Cream Puff War >\n'
    '09. Silvio > Tequila > Silvio >\n'
    "10. Good Lovin'\n"
    '\n'
    'Set II Disc 2: 69:34\n'
    '\n'
    '01. Peggy-O@ >\n'
    '02. Me and My Uncle@\n'
    '03. Quinn The Eskimo@ >\n'
    '04. The Other One >\n'
    '05. Samson and Delilah >\n'
    '06. Stuff\n'
    '07. Come Together>\n'
    '08. Going Down The Road Feeling Bad\n'
    '\n'
    '\n'
    'Encore:\n'
    '\n'
    '09. Ripple / Birthday Rap\n'
    '\n'
    '\n'
    '*-Distinct Milestones signature riffs during most of the opening Jam.'
)
RATDOG_2008_11_16_TRACKS = ['Milestones Jam* >', 'Here Comes Sunshine >', 'Mama Tried', "It's All Over Now, Baby Blue", 'Mission in the Rain', 'Lucky Enough >', 'Big Boss Man', 'Cream Puff War >', 'Silvio > Tequila > Silvio >', "Good Lovin'", 'Peggy-O@ >', 'Me and My Uncle@', 'Quinn The Eskimo@ >', 'The Other One >', 'Samson and Delilah >', 'Stuff', 'Come Together>', 'Going Down The Road Feeling Bad', 'Ripple / Birthday Rap']
RATDOG_2008_11_16_SOURCES = {}
RATDOG_2008_11_16_TODAY = ['1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '2', '2', '2', '2', '2', '2', '2', '2', '2']

# soulive-2001-12-15: md_Soulive2001-12-15sbd.shn.json (description)
SOULIVE_2001_12_15 = (
    'Set 1 disc 1\n'
    "1. steppin'\n"
    '2. cannonball\n'
    '3. 1 in 7 (techno intro remix) \n'
    '4. azucar\n'
    '5. hurry up... and wait\n'
    '\n'
    'Set 2 disc 2\n'
    '1. uncle jr.\n'
    "2. it's your thing\n"
    '3. lenny->\n'
    '4. turn it out'
)
SOULIVE_2001_12_15_TRACKS = ["Steppin'", 'Cannonball', 'soulive2001-12-15d1.shnf/soulive2001-12-15d1t03.mp3', 'Azucar', 'Hurry Up... and Wait', 'uncle jr', "it's your thing", 'lenny->', 'turn it out', 'soulive2001-12-15d2.shnf/soulive2001-12-15d2t05.mp3']
SOULIVE_2001_12_15_SOURCES = {3: 'unresolved', 10: 'unresolved'}
SOULIVE_2001_12_15_TODAY = ['1', '1', '1', '1', '1', '1', '1', '1', '1', '1']

# soundtribesector9-2007-07-08: md_sts92007-07-08.mk4.flac16.json (description)
STS9_2007_07_08 = (
    'Set 1/Disc 1:\n'
    '01 - Intro/Murph\n'
    '02 - Instantly \n'
    '03 - Move my Peeps\n'
    '04 - Velez *\n'
    '05 - Unquestionable Supremacy\n'
    '06 - Ramone & Emiglio\n'
    '07 - The Rabble\n'
    '08 - Open e\n'
    '\n'
    'Set 2/Disc 2:\n'
    '01 - Lo Swaga\n'
    '02 - 1103\n'
    '03 - One a Day\n'
    '04 - 303* >  \n'
    '05 - Hip-hop* >Surreality* > Eb* \n'
    '06 - Blu Mood\n'
    '\n'
    'Set 2/Disc 3:\n'
    'Encore 1\n'
    '01 - Baraka\n'
    '02 - Evasive Maneuvers > Kamuy\n'
    'Encore 2\n'
    '03 - Grow'
)
STS9_2007_07_08_TRACKS = ['Instantly', 'Move my Peeps', 'Velez *', 'Unquestionable Supremacy', 'Ramone & Emiglio', 'The Rabble', 'Open e', 'Lo Swaga', '1103', 'One a Day', '303 Improv*', 'Hip-hop* >Surreality* > Eb*', 'Blu Mood', 'Baraka', 'Evasive Maneuvers > Kamuy', 'Grow']
STS9_2007_07_08_SOURCES = {11: 'sibling-align'}
STS9_2007_07_08_TODAY = ['1', '1', '1', '1', '1', '1', '1', '1', '2', '2', '2', '2', '2', 'encore', 'encore', 'encore']

# thecodetalkers-2003-10-31: md_codetalkers2003-10-31.flac16.json (description)
CODETALKERS_2003_10_31 = (
    'DISC 1 SET ONE\n'
    '01 Nash\n'
    "02 I'm So Glad\n"
    '03 Lima\n'
    '04 Basically Frightened*\n'
    '05 Body in the Lake\n'
    '06 When The World Comes Tumbling Down\n'
    '\n'
    'DISC 2 SET TWO\n'
    '01 Saturn!\n'
    '02 Turn On Your Lovelight\n'
    '03 Get to Know You Better >>\n'
    "04 Fixin' to Die  \n"
    "05 ENCORE: Diggin' Up Bones"
)
CODETALKERS_2003_10_31_TRACKS = ['Nash (7:53)', "I'm So Glad (8:19)", 'Lima (14:50)', 'Basically Frightened* (10:18)', 'Body in the Lake (8:37)', 'When The World Comes Tumbling Down (11:40)', 'Saturn! (10:50)', 'Turn On Your Lovelight (10:41)', 'Get to Know You Better >> (10:04)', "Fixin' to Die (9:17)", "ENCORE: Diggin' Up Bones (6:54)"]
CODETALKERS_2003_10_31_SOURCES = {}
CODETALKERS_2003_10_31_TODAY = ['1', '1', '1', '1', '1', '1', '1', '1', '1', '1', 'encore']

# corblund-2004-11-04: md_corblund2004-11-04.emc709.flac.json (description)
CORBLUND_2004_11_04 = (
    'The Corb Lund Band\n'
    'Live At The Times Change High And Lonesome Club\n'
    'Winnipeg, Manitoba\n'
    'November 5, 2004\n'
    'Three Sets\n'
    'Taped from the front row & Transferred by Redseed Mobile\n'
    '\n'
    'EMC709->MT-877\n'
    '\n'
    "Transfer done with a wicked soundcard at my buddy's studio\n"
    '\n'
    'Sound is excellent, especially for rig used\n'
    '\n'
    'Disc/Set1\n'
    '01 (Gonna) Shine up My Boots\n'
    '02 Expectation and the Blues\n'
    '03 Apocalyptic Modified Blues\n'
    "04 The Counterfeiter's Blues\n"
    '05 No Roads Here\n'
    '06 Short Native Grasses\n'
    '07 Sixteen Tons\n'
    '08 The Big Bitch Butch Bull Fiddle\n'
    "09 The Truck Got Stuck Talkin' Blues\n"
    "10 We Used To Ride 'em\n"
    "11 Buckin' Horse Rider\n"
    '12 Okie From Muskogee\n'
    '\n'
    'Disc/Set2\n'
    '01 Roughest Neck Around\n'
    "02 Daughter Don't You Marry No Guitar Picker\n"
    '03 The Cover of The Rolling Stone\n'
    '04 Heavy And Leaving\n'
    '05 Good Copenhagen Is Better Than Bad Cocaine\n'
    '06 Time To Switch To Whiskey\n'
    '07 Mora (Blackberry)\n'
    '08 Where Is My Soldier\n'
    '09 Seven Spanish Angels\n'
    '10 A Leader on Losing Control\n'
    '11 All I Wanna Do Is Play Cards\n'
    '12 Five Dollar Bill\n'
    "13 She Won't Come To me\n"
    '14 Always keep An Edge on Your Knife\n'
    '\n'
    'Disc/Set3\n'
    "01 Workin' Man Blues\n"
    '02 Now I Must Leave\n'
    '03 Eating Me Alive\n'
    '04 Crazy\n'
    '05 Lament For Lester Cousins\n'
    '06 Case Of The Winde Soaked Preacher\n'
    '07 Folsom Prison Blues\n'
    '08 (Gonna) Shine up My Boots\n'
    '09 Are You Sure Hank Done it This Way\n'
    '10 Spanish Armada\n'
    '11 On The Road Again\n'
    '\n'
    'Please share but NEVER EVER encode to mp3 or other lossy formats.'
)
CORBLUND_2004_11_04_TRACKS = ['Gonna) Shine up My Boots', 'Expectation and the Blues', 'Apocalyptic Modified Blues', "The Counterfeiter's Blues", 'No Roads Here', 'Short Native Grasses', 'Sixteen Tons', 'The Big Bitch Butch Bull Fiddle', "The Truck Got Stuck Talkin' Blues", "We Used To Ride 'em", "Buckin' Horse Rider", 'Okie From Muskogee', 'Roughest Neck Around', "Daughter Don't You Marry No Guitar Picker", 'The Cover of The Rolling Stone', 'Heavy And Leaving', 'Good Copenhagen Is Better Than Bad Cocaine', 'Time To Switch To Whiskey', 'Mora (Blackberry)', 'Where Is My Soldier', 'Seven Spanish Angels', 'A Leader on Losing Control', 'All I Wanna Do Is Play Cards', 'Five Dollar Bill', "She Won't Come To me", 'Always keep An Edge on Your Knife', "Workin' Man Blues", 'Now I Must Leave', 'Eating Me Alive', 'Crazy', 'Lament For Lester Cousins', 'Case Of The Winde Soaked Preacher', 'Folsom Prison Blues', 'Gonna) Shine up My Boots', 'Are You Sure Hank Done it This Way', 'Spanish Armada', 'On The Road Again']
CORBLUND_2004_11_04_SOURCES = {}
CORBLUND_2004_11_04_TODAY = ['1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1', '1']

N_FORM_CASES = {
    "ratdog-2008-11-16": (RATDOG_2008_11_16, RATDOG_2008_11_16_TRACKS, RATDOG_2008_11_16_SOURCES,
                          RATDOG_2008_11_16_TODAY, True),
    "soulive-2001-12-15": (SOULIVE_2001_12_15, SOULIVE_2001_12_15_TRACKS,
                           SOULIVE_2001_12_15_SOURCES, SOULIVE_2001_12_15_TODAY, False),
    "soundtribesector9-2007-07-08": (STS9_2007_07_08, STS9_2007_07_08_TRACKS,
                                     STS9_2007_07_08_SOURCES, STS9_2007_07_08_TODAY, False),
    "thecodetalkers-2003-10-31": (CODETALKERS_2003_10_31, CODETALKERS_2003_10_31_TRACKS,
                                  CODETALKERS_2003_10_31_SOURCES, CODETALKERS_2003_10_31_TODAY,
                                  False),
    "corblund-2004-11-04": (CORBLUND_2004_11_04, CORBLUND_2004_11_04_TRACKS,
                            CORBLUND_2004_11_04_SOURCES, CORBLUND_2004_11_04_TODAY, False),
}


@pytest.mark.parametrize("slug", sorted(N_FORM_CASES))
def test_disc_and_set_real_cases_own(slug):
    text, names, sources, today, family = N_FORM_CASES[slug]
    d = decide_taper(_mk_src(names, today, sources), {"description": text},
                     aliases=GD_SHORTHAND if family else {}, today_sets=today)
    assert d.placement is not None, d.reason
    assert d.source == "description"


def test_disc_and_set_real_case_labels():
    tt = read_taper_structure(RATDOG_2008_11_16)  # "Set I Disc 1: 74:16"
    assert tt.asserts is True and runs(tt) == ["1", "2", "encore"]
    assert "74:16" not in titles(tt) and label(tt, "Peggy-O@") == "2"
    tt = read_taper_structure(CORBLUND_2004_11_04)  # "Disc/Set1" ... "Disc/Set3"
    assert tt.asserts is True and runs(tt) == ["1", "2", "3"]
    assert label(tt, "Roughest Neck Around") == "2" and label(tt, "Workin' Man Blues") == "3"
    tt = read_taper_structure(STS9_2007_07_08)  # "Set 2/Disc 3:" continues set 2
    assert runs(tt) == ["1", "2", "encore"] and label(tt, "- Blu Mood") == "2"


@pytest.mark.parametrize("h1, h2", [
    ("Set 1 Disc 1", "Set 2 Disc 2"),
    ("Set I Disc I", "Set II Disc II"),
    ("Set One Disc One", "Set Two Disc Two"),
    ("Set I Disc 1: 74:16", "Set II Disc 2: 69:34"),
    ("set 1 - disc 1", "set 2 - disc 2"),
    ("Set 1-Disk 1", "Set 2-Disk 2"),
    ("Set 1/Disc 1:", "Set 2/Disc 2:"),
    ("set 1 / disc 1", "set 2 / disc 2"),
    ("Disc I 1st Set", "Disc II 2nd Set"),
    ("Disk 1: Set 1", "Disk 2: Set 2"),
    ("Disc 1, Set 1", "Disc 2, Set 2"),
    ("DISC 1 SET ONE", "DISC 2 SET TWO"),
    ("DISC 01:SET I :", "DISC 02:SET II"),
    ("disc 01 [Set I]", "disc 02 [Set II]"),
    ("CD1 Set 1", "CD2 Set 2"),
    ("CD 1 - Set 1", "CD 2 - Set 2"),
    ("Disc/Set1", "Disc/Set2"),
    ("Disc 1: Set 1", "Disc 2: Set 2"),
    ("~Disc 1: Set 1~", "~Disc 2: Set 2~"),
    ("Disk 1 (Set 1)", "Disk 2 (Set 2)"),
])
def test_disc_and_set_shapes_read_as_set_m(h1, h2):
    tt = read_taper_structure(f"{h1}\nBertha\nSugaree\n{h2}\nScarlet Begonias\nRipple\n")
    assert tt.asserts is True and runs(tt) == ["1", "2"], tt.reason
    assert titles(tt) == ["Bertha", "Sugaree", "Scarlet Begonias", "Ripple"]


def test_disc_and_set_repeated_set_is_a_continuation():
    tt = read_taper_structure("Set 1 Disc 1\nBertha\nSet 2 Disc 2\nSugaree\n"
                              "Set 2 Disc 3\nRipple\nEncore:\nTruckin\n")
    assert tt.asserts is True and runs(tt) == ["1", "2", "encore"]
    assert label(tt, "Ripple") == "2"


@pytest.mark.parametrize("line", [
    "SET 1/2",                # set 1 of 2: not admitted
    "(Start Set 2)",          # not admitted
    "(start of Set II)",
    "Set II (Disc 2)",        # not in the ruling's list
    "Disc 2 Set Break",       # no set number
    "Disc 2 - NRPS",          # an act header
    "Disc 1 set in Boston",   # word-bounded token
    "CD2 Set 2 Part1",        # a trailing word is no tail
    "Disk 3: Encore",         # disc-and-ENCORE is not in the ruling
])
def test_shapes_the_ruling_does_not_admit(line):
    tt = read_taper_structure(f"Set 1:\nBertha\n{line}\nSugaree\nSet 2:\nRipple\n")
    assert label(tt, "Sugaree") == "1"
    assert label(tt, "Ripple") == "2"
    assert tt.has_encore is False


# Item 7, ruling (d), keep today's encore: no taper encore marker, and today's structure has
# an encore after the taper's last placed numbered boundary, so the taper owns nothing.
# gratefuldead-1968-12-07: md_gd1968-12-07.sbd.miller.88674.sbeok.flac16.json (description)
GD_1968_12_07 = (
    'Set 1\n'
    '\n'
    'Dark Star  ->\n'
    'Saint Stephen  ->\n'
    'The Eleven  \n'
    "% Death Don't Have No Mercy  \n"
    '% Cryptical Envelopment  ->\n'
    'Drums  ->\n'
    'The Other One  ->\n'
    'Cryptical Envelopment  ->\n'
    'Jam ->\n'
    'New Potato Caboose  \n'
    '%   \n'
    '\n'
    'Set 2\n'
    '\n'
    'Rosemary  \n'
    '\n'
    'He Was A Friend Of Mine  \n'
    '\n'
    'It Hurts Me Too  \n'
    '\n'
    'Morning Dew  ->\n'
    'And We Bid You Good Night'
)
GD_1968_12_07_TRACKS = ['Dark Star >', 'St Stephen ->', 'The Eleven', "Death Don't Have No Mercy", "That's It For The Other One ->", 'New Potato Caboose', 'Rosemary', 'He Was A Friend Of Mine', 'It Hurts Me Too', 'Morning Dew ->', 'And We Bid You Goodnight']
GD_1968_12_07_TODAY = ['1', '1', '1', '1', '1', '1', '2', '2', '2', '2', 'encore']


def test_todays_encore_real_case_is_kept():
    # The taper wrote Set 1 / Set 2 and no encore; today ships `And We Bid You Goodnight` as
    # the encore. Owning would fold it into set 2.
    tracks = _mk_today(GD_1968_12_07_TRACKS, GD_1968_12_07_TODAY)
    d = decide_taper(tracks, {"description": GD_1968_12_07}, aliases=GD_SHORTHAND,
                     today_sets=GD_1968_12_07_TODAY)
    assert d.placement is None and d.reason == "veto: today's encore"
    # The same tape with today's encore relabelled set 2: the taper owns it as before.
    flat = ["1"] * 6 + ["2"] * 5
    d = decide_taper(tracks, {"description": GD_1968_12_07}, aliases=GD_SHORTHAND,
                     today_sets=flat)
    assert d.placement is not None and d.placement.boundaries == (6,)


TODAY_ENC_TRACKS = ["Bertha", "Let It Grow", "Scarlet Begonias", "Truckin", "Ripple"]


@pytest.mark.parametrize("today, owned", [
    (["1", "1", "2", "2", "encore"], False),       # today's encore after the last break
    (["1", "1", "encore", "encore", "encore"], False),  # ... starting right at it
    (["1", "1", "2", "2", "2"], True),             # no encore today
    (["1", "1", "1", "1", "1"], True),
    (["encore", "1", "2", "2", "2"], True),        # today's encore before the last break
])
def test_todays_encore_rule_directions(today, owned):
    text = "Set 1: Bertha, Let It Grow\nSet 2: Scarlet Begonias, Truckin, Ripple\n"
    d = decide_taper(mk(TODAY_ENC_TRACKS), {"description": text}, aliases={}, today_sets=today)
    assert (d.placement is not None) is owned, d.reason
    if not owned:
        assert d.reason == "veto: today's encore"
    else:
        assert d.placement.boundaries == (2,)


def test_todays_encore_rule_off_when_the_taper_marks_an_encore():
    text = "Set 1: Bertha, Let It Grow\nSet 2: Scarlet Begonias, Truckin\nEncore: Ripple\n"
    d = decide_taper(mk(TODAY_ENC_TRACKS), {"description": text}, aliases={},
                     today_sets=["1", "1", "2", "encore", "encore"])
    assert d.placement is not None and d.placement.boundaries == (2, 4)


def test_todays_encore_rule_uses_the_last_of_three_sets():
    text = "Set 1: Bertha\nSet 2: Let It Grow, Scarlet Begonias\nSet 3: Truckin, Ripple\n"
    tracks = mk(TODAY_ENC_TRACKS)
    # today's encore sits inside the taper's set 2, before the last break (after track 3)
    d = decide_taper(tracks, {"description": text}, aliases={},
                     today_sets=["1", "2", "encore", "3", "3"])
    assert d.placement is not None and d.placement.boundaries == (1, 3)
    d = decide_taper(tracks, {"description": text}, aliases={},
                     today_sets=["1", "2", "2", "3", "encore"])
    assert d.placement is None and d.reason == "veto: today's encore"


# Fix round 1 (t12-fix1), finding 1: a numbered line the comma rule keeps whole may hold two
# real songs (`05 - Native End, Open E`). `fuzzy_title_eq` tolerates a dropped tail, so the
# merged item matches its first song alone and would hide its second song from placement's
# checks. Its comma parts now count for the "other side" and merged-span checks, and a
# boundary item whose later comma part names a song on the tape declines.
COMMA_MERGE_TEXT = ("Set 1\n1. Bertha\n2. Sugaree\n3. Jack Straw, Ripple\n"
                    "Set 2\n4. Scarlet Begonias\n5. Fire on the Mountain\n")


def test_comma_merged_boundary_item_never_moves_a_break():
    tt = read_taper_structure(COMMA_MERGE_TEXT)
    assert label(tt, "Jack Straw, Ripple") == "1"
    # Ripple (the taper's set 1) shares a track with Scarlet Begonias (set 2): owning would
    # label Ripple set 2, a moved break.
    tracks = mk(["Bertha", "Sugaree", "Jack Straw", "Ripple > Scarlet Begonias",
                 "Fire on the Mountain"])
    d = decide_taper(tracks, {"description": COMMA_MERGE_TEXT}, aliases={}, today_sets=["1"] * 5)
    assert d.placement is None
    assert d.reason.startswith("unplaced: 1|2"), d.reason


def test_comma_merged_boundary_item_on_separate_tracks_declines():
    # With Ripple on its own track the taper's break does fall after Ripple, but which comma
    # part closes the set is exactly the one-title question the comma rule cannot answer
    # (CLAUDE.md's A2: no clean discriminator), so the taper owns nothing rather than guess.
    tracks = mk(["Bertha", "Sugaree", "Jack Straw", "Ripple", "Scarlet Begonias",
                 "Fire on the Mountain"])
    d = decide_taper(tracks, {"description": COMMA_MERGE_TEXT}, aliases={}, today_sets=["1"] * 6)
    assert d.placement is None
    assert "comma" in d.reason, d.reason


def test_comma_part_counts_for_the_other_side_check():
    # A comma part on set 1's side names set 2's first song: a title repeated across the
    # boundary, so unplaced (it was hidden inside the merged item before).
    text = ("Set 1\n1. Bertha\n2. Jam, Drums\n3. Sugaree\nSet 2\n4. Drums\n5. Ripple\n")
    tracks = mk(["Bertha", "Jam", "Sugaree", "Drums", "Ripple"])
    d = decide_taper(tracks, {"description": text}, aliases={}, today_sets=["1"] * 5)
    assert d.placement is None
    assert d.reason == "unplaced: 1|2 'Drums' also occurs on the other side", d.reason


# jackiegreene-2010-12-31: md_jg2010-12-31-Schoepsmk4.json (description)
JG_2010_12_31 = (
    'Set 1\n'
    '\n'
    "01. Don't let the Devil take your mind\n"
    "02. I'm so Gone\n"
    '03. Medicine\n'
    '04. A Moment of Temporary Color\n'
    '05. New Speedway Boogie\n'
    '06. Shaky Ground\n'
    "07. When You're Walking Away\n"
    "08. I'm Tore Down\n"
    '09. Farewll, solong, Goodby\n'
    '\n'
    'Set 2\n'
    '\n'
    '01. Mexican Girl\n'
    '02. Shaken\n'
    '03. So Hard to Find My Way\n'
    '04. Auld Lang Syne\n'
    '05. Tell Mama\n'
    '06. Uphill Mountain\n'
    '07. Count Down to New Years > After Midnight\n'
    '08. Hollywood >\n'
    '09. Tomorrow Never Knows > Taxman > Tomorrow Never Knows \n'
    '10. Scarlet Bagonias\n'
    '11. Gone Wandering\n'
    '12. Animal\n'
    '13. Ball and Chain'
)
JG_2010_12_31_TRACKS = ["Don't let the Devil take your mind", "I'm so Gone", 'Medicine', 'A Moment of Temporary Color', 'New Speedway Boogie', 'Shaky Ground', "When You're Walking Away", "I'm Tore Down", 'Farewll, solong, Goodby', 'Mexican Girl', 'Shaken', 'So Hard to Find My Way', 'Auld Lang Syne', 'Tell Mama', 'Uphill Mountain', 'Count Down to New Years > After Midnight', 'Hollywood >', 'Tomorrow Never Knows > Taxman > Tomorrow Never Knows', 'Scarlet Bagonias', 'Gone Wandering', 'Animal', 'Ball and Chain']
JG_2010_12_31_TODAY = ['1', '1', '1', '1', '1', '1', '1', '1', '1', '2', '2', '2', '2', '2', '2', '2', '2', '2', '2', '2', '2', '2']


def test_single_title_comma_boundary_item_still_owns():
    # `09. Farewll, solong, Goodby` is one real title on one track, closing set 1.
    tracks = _mk_today(JG_2010_12_31_TRACKS, JG_2010_12_31_TODAY)
    d = decide_taper(tracks, {"description": JG_2010_12_31}, aliases={},
                     today_sets=JG_2010_12_31_TODAY)
    assert d.placement is not None and d.placement.boundaries == (9,), d.reason


def test_trailing_dots_are_not_an_annotation():
    """(pin changed, fix round 1) Ruling (b) admits only a `(duration|time)` annotation; the
    `...` the Checkpoint A round also admitted is dropped (controller ruling R8)."""
    for h1, h2 in (("Disc 1 - Set I...", "Disc 2 - Set II..."), ("Set 1...", "Set 2…")):
        tt = read_taper_structure(f"{h1}\nBertha\nSugaree\n{h2}\nScarlet Begonias\nRipple\n")
        assert tt.asserts is False, (h1, tt)


def test_comma_inside_parentheses_is_no_song_separator():
    # joerussosalmostdead-2015-05-09's credits: `Dancing In The Streets @ (SM, NA)` and
    # `Music Never Stopped (SM,NA)` on opposite sides of the break. A comma inside the
    # parenthetical credit splits no song, so `NA)` is not a title repeated across it.
    text = ("Set One:\n01. Dancing In The Streets @ (SM, NA)\n02. Cassidy (SM, NA)\n"
            "03. Not Fade Away ^ # (All)\nSet Two:\n04. Music Never Stopped (SM,NA)\n"
            "05. Morning Dew (TH)\n")
    tracks = mk(["Dancing In The Streets", "Cassidy", "Not Fade Away", "Music Never Stopped",
                 "Morning Dew"])
    d = decide_taper(tracks, {"description": text}, aliases={}, today_sets=["1"] * 5)
    assert d.placement is not None and d.placement.boundaries == (3,), d.reason
