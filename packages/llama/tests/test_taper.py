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
    # "~Disc 1: Set 1+Encore~" is not even a recognised form (a colon disc line), so it
    # changes no label, and the later "Encore" starts the encore. "~Disc 2: Set 2~" is not
    # recognised either, so no numbered set is asserted here at all.
    tt = read_taper_structure(LOTUS_2005_10_15)
    assert tt.has_encore is True
    assert label(tt, "Lucid Awakening") == "1"
    assert label(tt, "Nematode") == "encore"
    assert tt.asserts is False and tt.reason == "one set"
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
    # The titles are exactly parse_setlist's (the reader only labels).
    assert titles(tt) == [i.title for i in parse_setlist(text).items if i.title in titles(tt)]


def test_signalpath_n_colon_is_not_a_marker():
    tt = read_taper_structure(SIGNAL_PATH)
    assert tt.asserts is False and tt.reason == "one set"
    assert tt.items[0] == TaperItem("1:  Escape Strategy", "1")
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
    "line, title",
    [
        ("E.Ville", "E.Ville"),
        ("B. E. Women", "B. E. Women"),
        ("E. Rutherford, NJ", "E. Rutherford"),
        ("I Know You Rider", "I Know You Rider"),
        ("J", "J"),
        ("Untitled #12", "Untitled #12"),
        ("E-Bow the Letter", "E-Bow the Letter"),
        ("(E)", "(E)"),
        ("[E]", "[E]"),
        ("E.", "E."),
    ],
)
def test_title_lookalikes_are_not_markers(line, title):
    tt = read_taper_structure(f"Set 1:\nBertha\n{line}\nSet 2:\nSugaree\n")
    assert tt.asserts is True
    assert tt.has_encore is False
    assert runs(tt) == ["1", "2"]
    assert label(tt, title) == "1"


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
