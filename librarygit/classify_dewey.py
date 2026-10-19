import argparse
import os
import re
import shutil
import sqlite3
import unicodedata
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB = os.getenv('DATABASE_FILE', os.path.join(BASE_DIR, 'library.db'))

CLASSIFICATION = """
770 ?   | (T)races of louis agassiz (photography, body and science,yesterday and today)
823.92  | (Work by Sarah Winman)
509     | 100 Big ideas (Science breakthroughs and inventions)
794.1   | 1064 Exercices pour bien débuter aux échecs
794.1   | 1064 Exercises pour bien débuter aux échecs
823.912 | 1984
551.5142 | 20 questions and answers about the ozone layer (2022)
823.0108 | 2019 shortlist
510.76  | 2026 Mongolian Mathematical Olympiad
909.83  | 21 Lessons for the 21st Centry
327.5106 | 24 years of FOCAC (The impact on china-africa cooperation)
507.8   | 365 Simple Science Experiments
823.92 ? | A  Different kind of Broken
823.914 | A COLOUR OF MAGIC
993.04092 | A DIFFERENT KIND OF POWER
363.1251 | A Deadly Wandering
515.39  | A First Course in Chaotic Dynamical Systems
518     | A First Course in Numerical Methods
004     | A Foundation for Computer Science
813.54  | A Game of Thrones
823.914 | A Grain of Wheat
843.92  | A Long Way from Douala
510.76  | A Mathematical Olympiad Primer
822.33  | A Midsummer Night's Dream
510.76  | A Problem Solver's Handbook
306.7   | A Quick and Easy Guide to Consent
398.2096762 | A School Certificate Course: Oral Literature
813.6   | A Spark of Light
531.34  | A Student's Guide to Rotational Motion
823.8   | A Tale of Two Cities
813.6   | A Thousand Splendid Suns
823.914 | A World of Strangers
823.92  | A Year of Marvellous Ways
523.1   | A brief history of time
305.42  | A decolonial Feminism
519.2   | A first course in Probability
515.39  | A first course in chaotic dynamical systems
869.3   | A general theory of Oblivion
954.92  | A history of Bangladesh
305.896 | A map to the Door of no Return
510.76  | A mathematical Olympiad companion
510.76  | A mathematical Olympiad primer 2
303.6096 | A moonless, Starless sky
512.72  | A prime puzzle
916.76204 | A rough guide to Kenya
221     | A selection of puzzle on the old testament
920 ?   | A son of two countries
823.914 | A wreath for Fr. Mayer
960     | AFRICA (AN ENCYLOPEDIA OF AN AMAZING CONTINENT)
658.05  | AI
823.92  | AMERICANAH
960     | AN AFRICAN HISTORY OF AFRICA (FROM DAWN OF HUMANITY TO INDEPENDENCE)
512.9   | AOPS Intermidiate Algebra Solutions Manual
511.6   | AOPS Intermidiate Counting & Probability Solutions Manual
511.6   | AOPS Introduction to Counting & Probability Solutions Manual
516     | AOPS Introduction to Geometry Solutions Manual
513     | AOPS Prealgebra
513     | AOPS Prealgebra Solutions Manual
512.1   | AOPS Precalculus Solutions Manual
510     | AS&A-Level Further Maths
523.01  | ASTROPHYSICS for PEOPLE in a HURRY
512.02  | Abstract Algebra (Third Edition)
371.26  | Achieving higher test scores on standardized tests
371.26  | Adequate yearly progress
531     | Advanced Level Mathematics Mechanics 2
519.5   | Advanced Level Mathematics Statistics 2
510     | Advanced Level Pure Mathematics
338.2728096 | Africa Crude Continent (The struggle for Africa's Oil Prize)
960     | Africa: A Biography of the Continent
960     | Africana (An Encyclopedia of an amazing continent)
823.92  | After you
813.6   | Akata Witch
967.6104 | Alice Lakwena & the Holy Spirits
305 ?   | All About People
428     | All round english
551.46  | Alpha Books Seas and Oceans
810     | America Literature
810     | American Literature (A chronological Approach)
823.92  | Americanah
954.035092 | An Autobiography
823.92  | An Elegy for Easterly
823.92  | An Orchestra of Minorities
069.09624 | An illustrated guide for visitors
510.76  | And beyond
813.6   | And the Mountains Echoed
813.6   | Angels & Demons
301     | Anthropology: A Graphic Guide
515     | AoPS Calculus
515     | AoPS Calculus Solutions Manual
510.76  | AoPS Competition Math For Middle school
512.9   | AoPS Intermediate Algebra
512.9   | AoPS Intermediate Algebra Solutions Manual
511.6   | AoPS Intermediate Counting & Probability solutions manual
512.9   | AoPS Introduction to Algebra
512.9   | AoPS Introduction to Algebra Solutions Manual
516     | AoPS Introduction to Geometry
512.7   | AoPS Introduction to Number Theory
511.6   | AoPS Introduction to counting & Probability
513     | AoPS Pre Algebra Solutions Manual
512.1   | AoPS Precalculus
510.76  | AoPS Volume 1: the Basics
510.76  | AoPS Volume 1: the Basics Solutions Manual
510.76  | AoPS Volume 2: and Beyond
510.76  | AoPS Volume 2: and Beyond Solution Manual
512.7   | AoPS introduction to Number Theory Solutions Manual
001.2 ? | Archetype To Zeitgeist
843.8   | Around the World in Eighty Days
822.33  | As you like it
523.01  | Astrophysics for People in a Hurry
551.5   | Atmosphere
158.1   | Atomic habits
741.5   | Aya
973.932092 | BECOMING
512.5   | Basic Linear Algebra
523.18  | Battle of the Big Bang
614.4   | Beating Back the Devil
973.932092 | Becoming
006.31  | Beginning with Machine Learning
150.724 | Behind the Shock Machine
613     | Being Healthy
813.6   | Beneath the lion's gaze
823.92 ? | Between Wild and Free
005.7   | Big Data
570     | Biology for Cambridge IGCSE Coursebook
570     | Biology for Cambridge IGCSE Workbook
570     | Biology for cambridge international AS & A Level Coursebook
909.0496 | Black History for everyday of the year
823.92  | Black Mamba boy
323.1196073 | Black Power 50
305.896 ? | Black Shamrocks
792.7028092 | Born a Crime
823.92  | Born on a Tuesday
968.83  | Botswana: An Historical Anthology
823.912 | Brave New World
823.912 | Brave new World
005.14  | C++ and C Debugging, Testing, and Reliability
570     | Cambridge IGCSE Biology
540.78  | Cambridge IGCSE Chemistry Practical Workbook
540     | Cambridge IGCSE Chemistry Revision Guide
540     | Cambridge IGCSE Chemistry fourth edition
540     | Cambridge IGCSE Chemistry workbook
428     | Cambridge IGCSE First Language English Coursebook
510     | Cambridge IGCSE Mathematics Core and Extended Coursebook
510     | Cambridge IGCSE Mathematics Extended Practice Book
510     | Cambridge IGCSE Mathematics core and Extended fifth edition
510     | Cambridge IGCSE Mathematics core and Extended fourth edition
530     | Cambridge IGCSE Physics
910     | Cambridge IGCSE and O Level Geography Fourth Edition
303.482 | Cambridge IGCSE and O Level Global Perspectives Coursebook
820     | Cambridge IGCSE and O Level Literature in English Coursebook
570     | Cambridge IGCSE® Biology
004     | Cambridge IGCSE® ICT Revision Guide
530     | Cambridge IGCSE® Physics
910     | Cambridge International AS & A Level Geography
531     | Cambridge International AS & A Level Mathematics Mechanics
004     | Cambridge International AS and A Level Computing
004     | Cambridge International AS&A Level Computer Science
303.482 | Cambridge International AS&A Level Global Perspectives & Research Coursebook
531     | Cambridge International AS&A Level Mathematics Mechanics
510     | Cambridge O Level Mathematics Vol. 1
510     | Cambridge O Level Mathematics Vol. 2
372.7   | Cambridge Primary Mathematics Module Seven Book 1
372.7   | Cambridge Primary Mathematics Module Seven Book 2
004     | Cambridge igcse ICT
372.7   | Cambridge primary mathematics module seven book 1
686.4   | Canon imageRUNNER 2320/2318 User's Guide
813.6   | Chain-Gang All-stars
428 ?   | Challenges
511.6   | Chapter 7 Combinatorics
808.83  | Chasing the Sun: Stories from Africa
967.804 | Cheche (Reminiscences of a Radical Magazine)
540.78  | Chemistry (Matter and Change) Laboratory Manual
540     | Chemistry for CAMBRIDGE AS & A LEVEL
540     | Chemistry for Cambridge IGCSE Coursebook
540     | Chemistry for Cambridge IGCSE Workbook
540     | Chemistry for Cambridge International AS&A Level Coursebook
540     | Chemistry for Cambridge International AS&A Level Workbook
540.78  | Chemistry: Matter and Change Laboratory Manual
394.12  | Chew on this
306.8   | Children of their fathers
031     | Children's Britannica Abbey to Arabs
031     | Children's Britannica Aran to Bee
031     | Children's Britannica Beech to Building
031     | Children's Britannica Epic to Furs
031     | Children's Britannica Gabon to Hedin
031     | Children's Britannica Jackal to Lomond
031     | Children's Britannica London to Moss
031     | Children's Britannica Moth to Oyster
031     | Children's Britannica Pacific to Pond
031     | Children's A to Z Encyclopedia
031     | Children's Britannica
782.5   | Choral Connections Treble Voices
305.509678 | Class Struggles in Tanzania
531     | Classical Mechanics
531     | Classical Mechanics 5th Edition
423 ?   | Collins
371.25  | Combination Classroom Planning Guide
005.1   | Competitive Programming
515.9   | Complex Variables: Second Edition
372.6   | Comprehension and writing assessments
004.22  | Computer Architecture: A Quantitative Approach
004     | Computer Science for Cambridge International AS&A Level Revision Guide
004     | Computer Science for Cambridge international AS&A Level
004     | Computer science for Cambridge IGCSE &O Level
510     | Concrete Mathematics
616.8914 | Couch Fiction: A Graphic Tale of Psychotherapy
513     | Counting
968.065 | Country of My Skull
510.76  | Crossing the Bridge
372.7   | Cumulative Practice Sets
006.8   | DEFYING REALITY
920 ?   | Dancing to My Own Drumbeat
005.73  | Data Structure & Their Algorithms
338.91096 | Dead Aid
813.6   | Deception Point
306.449 | Decolonising The Mind
306.449 | Decolonising the Mind
650.1   | Deep Work
220.9505 | Die Beste Vir Almal
813.54  | Digital Fortress
297     | Discovering Religions (Islam)
270.1   | Discovering the Bible: The Expansion of Christianity
956.1015 | Discovering the Ottomans
270.1   | Discovering the bible the expansion of christianity
511     | Discrete Mathematics (Third Edition)
511     | Discrete Mathematics with Graph theory and Combinations
511.5   | Dots and Lines
059 ?   | Dr. Satan's Echo Chamber (Chimurenga 12 & 13)
823.92  | Dream Count
823.92  | Dust
823.914 | Dustbin Baby
330     | Economics for Cambridge IGCSE and O Level Coursebook
330     | Economics for Cambridge International AS&A Level Coursebook
510     | Edexcel GCSE Mathematics: Foundation
510     | Edexcel GCSE Mathematics: Intermediate
823.914 | Efuru
813.54  | Einstein`s dreams
152.4   | Emotional Intelligence
428     | English Communication Skills in the New Millenium
428     | English Language for Cambridge International AS&A Level Coursebook
303.44  | Enlightenment Now
199.492 | Erasmus of Christendom
516.2   | Euclid (the thirteen books of the elements)
516.2   | Eucliedean Geometry in mathematical olympiads
371.3 ? | Every Student Learns
371.3 ? | Every student Learns
372.7   | Everyday Mathematics Skills Link Cumulative Practice tests
372.7   | Everyday mathematics cumulative practice sets
823.92  | Everything Under
516     | Everything you need to ace Geometry In One Big Fat Notebook
813.6   | Everything, Everything
158.1   | Failosophy
823.914 | Far And Beyond
530     | Fear of a Black Universe… An Outsider's Guide to the Future of Physics
305.42  | Feminist issues in Gandhian Thought
371.822092 | Finding my way
123.3   | Fooled by Randomness
810.8896073 | Fire devoted to younger negro artist
428     | First Language English
510.76  | First steps for problem solvers
730.96762 | Form
730.96762 | Form - Contempary view of Kenyan Sculpture
650.1 ? | Freedom to fail
001.2 ? | From Archtype to Zeitgeist
512.7   | From Zero to Infinity
709.2   | Fugitive
305.42  | Fugitive Feminism
005.1   | Fundamentals of Computer Algorithms
510     | GCSE 9-1 Mathematics
960     | GREAT KINGDOMS OOF AFRICA
823.92 ? | Generation of Destruction
910     | Geography for Cambridge IGCSE and O Level Coursebook
736.982 | Geometrische Origami
070.5   | Getting It Published
158.5   | Getting to Yes
966.7   | Ghana: A Portrait
909.0971241 | Ghosts of Empire
823.92  | Ginger Bread
540.78  | Glencoe Chemistry - Laboratory Manual
808.8   | Glencoe Literature
808.8   | Glencoe Literature (3)
808.8   | Glencoe literature (4)
327.6   | Global Africa
307.76  | Global City Local Identity
510     | God Created the Integers
813.6   | Goddess of the River
823.92 ? | Good intentions Evil deeds
823.92  | Grace land
823.8   | Great Expectations
248.4   | Guided to Christian Growth
032.02  | Guinness World Records 2020
822.92  | HARRY POTTER AND THE CURSED CHILD
658.05  | HBR's 10 Must Reads on AI
909.83  | HOMO DEUS
822.33  | Hamlet
570     | Harcourt Science Life sciences
823.8   | Hard Times
823.914 | Harry Potter and The Order of the Phoenix
823.914 | Harry Potter and the Deathly Hallows
823.914 | Harry Potter and the Goblet of Fire
823.914 | Harry Potter and the Half-Blood prince
823.914 | Harry Potter and the Philosopher's Stone
823.914 | Harry Potter and the Prisoner of Azkaban
823.914 | Harry potter and the Chamber of Secrets
823.914 | Head Above Water
616.12  | Heart: A History
813.54  | Henry and mudge in puddle trouble
823.912 | Hickory, Dickory, Dock
510.92  | Hidden Figures - The American Dream and the Untold Story of the Black Women Mathematicians Who Helped Win the Space Race
823.914 | Hiding in Plain Sight
823.914 | His Dark Materials The Golden Compass
823.914 | His Dark Materials: The Amber Spyglass
823.914 | His Dark Materials: The Subtle Knife
954.8   | History of south India for children
909.82  | History scene in the modern world
813.52  | Hitting a Straight Lick with a Crooked Stick
813.54  | Holes
500     | Holt Science
814.54  | Home (Social Essays)
811.6   | Home Body
813.6   | Homegoing
388     | How Do People Travel?
709.05 ? | How Far - How Near - Global
813.6   | How to Read the Air
158.2   | How to Win Friends and Influence People
005.3   | How to build a billion dollar app
793.73  | How to think, 50 puzzles for lateral thinking
793.74  | How to think, Numerical Thinking
153.4   | How to think, Objective Thinking
304.2   | Humans Versus Nature
510.76  | Hungarian Mathematical Olympiad (1964-1997)
812.6   | I Am an Emotional Creature
972.91064092 | I Embrace You With All My Revolutionary Fervor: Letters 1947–1967
371.822095491 | I am Malala
362.19697 | I die but the memory lives on
004     | IGSCE and O Level Computer Science Second Edition
512.0076 | IMO Problems, Theorems and Methods Algebra
511.6076 | IMO Problems, Theorems and Methods Combinatorics
516.0076 | IMO Problems, Theorems and Methods Geometry
512.7076 | IMO Problems, Theorems and Methods Number Theory
823.92 ? | If she were Alive
960 ?   | Imaginery Crimes
510     | Impact Maths 1R
510     | Impact Maths 2R
510     | Impact Maths 3R
909     | In praise of forgetting
966.9405092 | In the shadow of a saint (a son's journey to understand his father's legacy)
398.2096 | Indaba My Children
510.76 ? | Individual contest
372.7   | Infant Mathematics Second Stage
813.6   | Inferno
607 ?   | Innovating The Future of Science And Technology
614.4   | Inside the Outbreaks
510.76  | Intermediate problems
531     | Intermidiate Mechanics
960.05  | International Journal of Africana Studies (2023)
960.05  | International Journal of Africana Studies (Spring-Summer 2019)
301     | Introducing Anthropology
514.742 | Introducing Fractals
220.61  | Introducing the Bible
512     | Introduction to Algebra
531     | Introduction to Classical Mechanics
512.7   | Introduction to Number Theory
535     | Introduction to Optics
511.6   | Introduction to combinatirics
511.6   | Introduction to combinatorics
512.97  | Introduction to inequalities
510.1   | Is Maths Real?
616.8521 | It Didn't Start With You
364.1323096762 | It is our turn to eat
510.76  | Italian Mathematical Contests 2024-2025
248.4   | JUDGING
823.8   | Jane Eyre
823.914 | Jolly Snow
967.6203092 | Jomo Kenyatta: Father of Harambee
222.2 ? | Joshua and the Children
248.4   | Judging when why how
823.92  | Juggling Truth
823.92  | Juggling Truths
967.804 | Julius K.Nyerere(Collected from speeches & writings)
967.804092 | Julius Nyerere (Becoming Nationalist)
967.804092 | Julius Nyerere (Humanist, Politician, Thinker)
967.804092 | Julius Nyerere (Rebellion Without Rebels)
967.804092 | Julius Nyerere (The Making of a Philosopher Ruler)
510.76  | Junior Problems (challenge Number four)
510.76  | Junior problems
364.66092 | Just Mercy (A story of justice and redemption)
709.6   | Kabbo Ka Muwala (The Girl's Basket)
362.196831 | Keeper
332.11092 | Keeping At It
510     | Key Stage 3 Maths
510     | Key stage 3 Classbook Maths
808.8   | Kwani
428 ?   | L Words
658.403 | LEFT BRAIN RIGHT STUFF
813.6   | LESSONS CHEMISTRY
823.912 | Lady Chatterley's Lover
372.6   | Language Arts
153.42  | Lateral Thinking
843.912 | Le petit Prince
658.4092 | Leaders eat last
813.6   | Let Us Descend
323.1196073 | Letter From Birmingham Jail
188     | Letters from a Stoic
823.92 ? | Letters to My Sisters
808.02  | Letters to a Writer of Color
796.72092 | Lewis Hamilton
813.6   | Life of PI
570.1   | Life's Edge (the search of what it means to be alive)
920 ?   | Lighting a Fire
519.72  | Linear Programming Game Theory
813.6   | Listening for Lucca
808     | Literacy and Rhetorical Techniques
823.92 ? | Little angels
741.5   | Logicomix  (an epic search for truth)
510     | London GCSE Mathematics - Intermediate
813.6   | Looking for Alaska
869.3   | Loose Ties
823.914 | Lord of Flies
510.76  | Lotus Mathematics Quiz Book
823.92  | Love in Colour
813.54  | Lucy
843.92  | Lullaby
823.92 ? | Lullaby for a small death
510.76  | MATH OLYMPIAD CONTEST PROBLEMS Volume 2
530.15  | MATHEMATICAL METHODS FOR PHYSICS AND ENGINEERIGN
510     | MEI Structured Mathematics
510     | MEI Structured Mathematics A2 Pure Mathematics
510     | MEI Structured Mathematics AS Further Pure Mathematics
519     | MEI Structured Mathematics Decision Mathematics 1
531     | MEI Structured Mathematics Mechanics 1
519.5   | MEI Structured Mathematics Statistics 2
372.7   | MK primary mathematics pupil's book for grade 1
510.76  | MOEMS CONTEST PROBLEMS VOLUME 3
822.33  | Macbeth
745.594 | Making Cards
330.01  | Making Sense of Chaos
510.76  | Mandelbrot Morsels
823.92  | Manifesto on Never Giving up
150.195 | Man's Search for Meaning
526     | Mapmatics how we navigate the world through numbers
813.54  | Masterworks
510.76  | Math Olympiad Contest Problems
510.76  | Math Out Loud
513.9   | Math Tricks
510.76  | Mathematical Olympiad in China
510     | Mathematics Pure 1
510.76  | Mathematics Quiz Book
372.7   | Mathematics Taks grade 1
510     | Mathematics core and Extended fourth edition
510     | Mathematics core and extended
510     | Mathematics course 2
372.4   | McGraw-Hill Reading
814.54  | Me Talk Pretty One Day
005.133 | MicroPython Programming Starter Kit
813.54  | Middle Passage
811.6   | Milk and Honey
823.92  | Mister pip
428 ?   | Modern Adventures
511.5   | Modern Graph Theory
305.896 ? | Modern day Black Alphabet
909.82  | Modern world history
843.914 | Monsieur Ibrahim et les Fleurs du Coran
428.2   | More Grammar Practice
823.912 | Mrs Dalloway
822.33  | Much Ado About Nothing
780 ?   | Music Correction
967.804092 | Mwalimu the Influence of Nyerere
305.896073 | My People: Five Decades of Writing About Black Lives
823.914 | My life in the bush of ghosts
531     | NEWTONS LAWS OF MOTION
307.76096762 | Nairobi Today (The paradox of a fragmented city)
510     | National Curriculum Mathematics
748 ?   | National Geographic - Glass
333.7   | Natural Resources
158.1   | Navigating your 20S and Beyond
813.6   | Nefertiti
531     | Nelson Mathematics for Cambridge International A Level Mechanics 1
823.914 | Nervous Conditions
516.2   | New problems in Euclidian Geometry
823.914 | No Time Like the Present
305.48896073 | No thanks (black, female and living in the martyr-free zone)
823.914 | None to Accompany Me
823.92  | Normal people
330.019 | Nudge
303.4   | Numbers Don't Lie
428     | O Level English
428.4   | Once a week comprehension
920 ?   | Once upon a time
500     | One Two Three... Infinity
966.9502092 | One Woman's Jihad
500     | One two three....Infinity
796.342092 | Open An Autobiography
372.4   | Open Court Reading
005.43  | Operating System Concepts (Windows XP Update Edition)
813.6   | Origin
306.85  | Our Family
371.37  | Out of the question
302     | Outliers
333.7096757 | Outlook Rwanda: Managing Natural Resources for Sustainable Development
813.6   | PERCY JACKSON AND THE LIGHTNING THEF
234.13  | POWER FOR THE MIRACULOUS
510.76  | PRACTICE COMPETITIONS FOR MATHCOUNTS VOLUME 2
005.74  | Palantir Foundry by Use-Cases
823.914 | Paradise
370 ?   | Pedagogy of Dissent
330.122 | People's Republic of Walmart
813.6   | Percy Jackson and The Battle of the Labyrinth
813.6   | Percy Jackson and The Greek Gods
813.6   | Percy Jackson and the Last Olympian
813.6   | Percy Jackson and the Sea of Monsters
813.6   | Percy Jackson and the titan's curse
612.662 | Period
932     | Pharaohs and Pyramids
428     | Phrasal Verbs
530     | Physics for Cambridge IGCSE
530     | Physics for Cambridge IGCSE Workbook
530.078 | Physics for Cambridge International AS&&A Level Practical Workbook
530     | Physics for Scientists and Engineers (Student Solutions Manual & Study Guide, Volume 2)
530     | Physics for cambridge international AS&A Level Coursebook
676.12  | Plants used in papermaking
823.912 | Poirot Investigates
510     | Practice book
808.8   | Prentice hall literature
823.7   | Pride and Prejudice
530     | Principles of physics
519.2   | Probability & Statistics 1 (cambridge international AS & A Level mathematics)
519.2   | Probability & Statistics 2 (cambridge international AS & A Level mathematics)
523.1   | Probable Impossibilities
372.7   | Problem solving book A math to know
510     | Proofiness
511.36  | Proofs from THE BOOK
510     | Pure Mathematics 1 ( Cambridge international AS&A Level Mathematics)
510     | Pure Mathematics 2&3 ( Cambridge international AS&A Level Mathematics)
823.92  | Purple Hibiscus
843.914 | Queen Pokou
306.766 | Queer: A Graphic History
607.1   | RCA Schools Technology Project
320.549 | REIMAGINING PAN- AFRICANISM
303.483 | Race After Technology
510.92  | Ramanujan (A jewel in the Crown)
299.676 | Rasta and Resistance
372.465 | Read Alone Phonics Stories
305.8   | Real friends talk about race
253.7   | Rebuild Small groups can make a difference
305.420968 | Reflecting Rogue (inside the mind of a feminist)
967.8232 | Revolutionary State making in Dar es Salaam
552     | Rocks & Minerals
813.54  | Roll of Thunder, Hear My Cry
794.1   | Russian Chess Masters volume 1
338.967571 | Rwanda inc.
510     | SMP Advanced Mathematics BOOk 1
510     | SMP Advanced Mathematics BOOk 4
510     | SMP Advanced Mathematics – Book 3 [Metric]
510     | SMP Revised Advanced Mathematics – Book 2
823.92 ? | Salty Dog
909     | Sapiens A Brief History of Humankind
248.4 ? | Saved by the king
823.92  | Say You're One of Them
507.6   | Science Taks Practice workbook
551.5142 | Scientific Assessment of Ozone Depletion(2022)
796.342092 | Searching For Novak
581.467 | Seeds and seedlings
510.76  | Selected Problems of the Vietnamese Mathematical Olympiad
158.1   | Self care kit to Mental Welness
510.76  | Senior Problems
823.92  | Serpentine
530     | Seven Brief Lessons on Physics
516     | Shape
303.4   | Shaping History (Cambridge Publication)
813.6   | She would be King
387     | Ships and Seafarers
510     | Simply Maths
814.54  | Sister Outsider
153.83  | Skin in the Game
823.92  | Small Worlds
843.914 | So Long a Letter
823.92 ? | So Much Work
305.800973 | So You Want to Talk About Race
843.914 | So long a letter
896.5   | Song of Lawino and Song of Ocol
782.27  | Songs of fellowship
782.27  | Songs of the vineyard
823.912 | Sons and Lovers
839.823 | Sophie's World
916.804 | Southern Africa
968.04  | Southern African Liberation Struggles 1
968.04  | Southern African Liberation Struggles 2
968.04  | Southern African Liberation Struggles 3
968.04  | Southern African Liberation Struggles 4
968.04  | Southern African Liberation Struggles 5
968.04  | Southern African Liberation Struggles 6
968.04  | Southern African Liberation Struggles 7
968.04  | Southern African Liberation Struggles 8
968.04  | Southern African Liberation Struggles 9
709.6 ? | Sowing Somankidi Coura
372.632 | Spelling and Vocabulary
813.52  | Steinbeck of mice and men
813.54  | Stories of your life and others
616.89  | Strangers to Ourselves
371.26 ? | Strategies for success
158.1   | Strength Finder 2.0
516     | String, Straightedge, & Shadow
069.09624 | Sudan National Museum
330     | SuperFreakonomics - Global Cooling, Patriotic Fever
266 ?   | Sushila's God
823.92  | Swing Time
796.48  | Sydney Olympic City
372.623 | TAAS Writing Test Preparation and Practice
158.1   | THE 7 HABITS OF HIGHLY EFFECTIVE PEOPLE
909     | THE WEBS OF HUMAN KIND
371.26  | Taks performance system
428 ?   | Target Book 3
607.1   | Technology Education Learning by Design
823.8   | Tess of the D'Urbervilles
500     | Texas Science (Grade 8)
813.54  | That Summer
610.285 | The AI Revolution in Medicine
873.01  | The Aeneid
967.5103 | The African Dream
341.249 | The African Union (Legal and Institutional Framework)
869.3   | The Alchemist
005.133 | The Art & Science of Java: An Introduction to Computer Science
355.02  | The Art of War
333.7   | The Atlas of Endangered Resources
823.914 | The Beautiful Ones Are Not Yet Born
823.912 | The Big Four
843.914 | The Blind Kingdom
823.92  | The Book of Dust
222.13  | The Book of Leviticus
813.6   | The Book of Night Women
823.0108 | The Caine Prize for African Writing 2010: A Life in Full and Other Stories
823.92  | The Cape Cod Bicycle War
823.92 ? | The Choice
614.4   | The Coming Plague
940.5318092 | The Complete Maus
823.92  | The Curious Incident of the Dog in the Night-Time
813.6   | The Da Vinci Code
188     | The Daily Stoic
529.1   | The Days of the Week
940.5318092 | The Diary of a Young Girl
824.914 | The Education of a British-protected child
539.7258 | The Elegant Universe
004.16  | The Elements of Computing Systems
823.914 | The Famished Road
813.6   | The Fault in our stars
353.0973 | The Fifth Risk
823.92  | The Forty Rules of Love
551.31 ? | The Frozen World
823.914 | The God of small things
823.0108 | The Goddess of Mtwara and other stories
813.6   | The Hate You Give (THUG)
823.92  | The Heavens May Fall
823.914 | The Hitchhiker's Guide to the Galaxy
823.912 | The Hobbit
220.52  | The Holy Bible
823.0108 | The Huza Press Anthology 2015
823.0108 | The Huza Press Anthology 2015 Versus Other Stories
813.54  | The Incredible Journey
823.914 | The Joys of Motherhood
530.11  | The Labyrinth of Time
808.8   | The Language of Literature
658.4092 | The Leadership Mindset Weekly
967.61  | The Legendally Kingdom - Buganda
843.912 | The Little Prince
567.9 ? | The Littlest Dinosaur
599.938 | The Lopsided Ape
823.912 | The Lord of The Rings
500     | The Magic of Reality: How We Know What's Really True
510.76  | The Mandelbrot Morsels
510.76  | The Mandelbrot Problem Book
793.74  | The Moscow Puzzles: 359 Mathematical Recreations
823.912 | The Mysterious Affair at Styles
853.914 | The Name of The Rose
823.92  | The New Policeman
591.513 | The Octopus and the Orangutan
823.92  | The Old Drift
330.122 | The People's Republic of Walmart
530     | The Physics of Superheroes
909.09724 | The Poorer Nations
158.1   | The Power of Habit
813.54  | The Reptile Room
371 ?   | The School
823.92  | The Schooldays of Jesus
823.92  | The Screaming Of The Innocent
510.9   | The Secret Lives of Numbers
813.54  | The Secret life of Bees
813.6   | The Sellout
510     | The Simpsons And Their Mathematical Secrets
362.19697 | The Skeptic's Guide to the Global AIDS Crisis
869.3   | The Spy
960.32  | The State of Africa
302.35  | The Stupidity Paradox
833.6   | The Swiss Family Robinson
813.6   | The Twelve-Mile Straight
839.313 | The Two Hearts of Kwasi Boachi
973.9   | The USA 1917–1980
813.6   | The Underground Railroad
808.8 ? | The Weganda Review
305.409678 | The World of Women Tanzania
843.914 | The Yambo Ouologuem Reader
511.6   | The backbone of Pascal's triangle
823.92  | The bastard of Istanbul
891.443 | The book of Dhaka
823.92  | The book of echoes
616.8527 | The book of feeling blue
612.8   | The brain that changes itself
823.914 | The colour of magic
363.7   | The environment
823.92  | The five sorrowful mysteries of andy africa
823.92  | The girl on the train
839.738 | The girl who saved the king of Sweden
823.8   | The great Adventure of Sherlock Holmes
967.827 | The history of Kiziba and its Kings
813.6   | The host
839.738 | The hundred year old man
813.6   | The kite Runner
808.8   | The language of literature (6)
338.2096 | The looting machine (warlords, tycoons,smugglers, and the systematic theft of africa's wealth)
972.983 | The loss of El Dorado
813.6   | The lost Symbol
372.87  | The music connection
227     | The prize of the high calling
823.914 ? | The prodigal Husband
341.24  | The quest for regional integration in the twenty first century
823.914 | The ring in the bush
823.92  | The screaming of Innocent
823.914 | The spy who came in from the cold
909     | The webs of human kind (Volume 2)
796.522 | The white spider
823.914 | The woman who walked into doors
530.01  | The world itself: Consciousness and the Everything of Physics
823.0108 ? | Their voices their stories
968.91051 | These Bones Will Rise Again
813.54  | These same long Bones
823.914 | Things Fall Apart
006.3   | Think AI
823.92 ? | This Thing Called Love
610.92  | This is going to Hurt
372.7   | Tiger math (Learning to graph from a baby tiger)
741.5954 | Tinkle Double Double Digest
306.362 | To Be a Slave
962.4043 | To Be or Not To Be (Sudan at Crossroads)
813.54  | To kill a Mockingbird
823.92  | Tomorrow I Become a Woman
248.32  | Too busy not to pray
511.6   | Topics in combinatorics
390     | Traditions Around the World
823.92 ? | Treeland (The land of laughter)
741.5   | Trust No Aunty
823.914 | Tsotsi
813.6   | Turtles all the way down
630     | Two Ears of corn
428.1   | Two way spelling
428.1   | Two-way Spelling
234     | UNMERITED FAVOR
333.72092 | Unbowed
869.3   | Under the Frangipani
510     | Understanding Pure Mathematics
920 ?   | Unfinished Journey
428 ?   | Upfront and Personal
863.64  | Violeta
428.24  | Visions
428.24  | Visions (Language-Literature-Content)
428.24  | Visions (Language-Literature-Content) A
612.399 | Vitamins
510.76  | Volume 1: the Basics
813.6   | WE ARE ALL COMPLETELY BESIDES OURSELVES
330     | WHY NATIONAS FAIL
328.73092 | Walking with the wind (A memoir of the movement)
823.92  | We Need New Names
305.42  | We Should All be Feminists
005.7   | Weapons of Math Destruction
823.914 | Weep Not, Child
303.483096 | What Do Science, Technology, and Innovation Mean from Africa
616.8521 | What Happened To you?
650.1 ? | What I did not learn at IIT
895.636 | What You Are Looking For Is in the Library
500 ?   | Whatever you thought think again
823.92  | When God was a Rabbit
823.92 ? | When Love Says Goodbye
059 ?   | Who No Know, Go Know - Chimurenga
307.1412 | Whose Reality Counts? Putting the First Last
232.954 | Wisdom Jesus
305.4 ? | Women making a difference
428     | Word perfect
331.1   | Work, employment and development
428.2   | Writing and Grammar communication in Action (Bronze level)
428.2   | Writing and Grammar communication in Action (Copper level)
428.2   | Writing and Grammar communication in Action (Silver level)
967.8   | Yes in my Lifetime
741.5973 | Yes, I'm Hot in This
823.92  | Yoruba Boy Running
823.92  | Zakes Little Suns MDA
818.54  | Zami (a new spelling of my name)
916.781 | Zanzibar & Pemba
495.183 | developing chinese (intermidiate speaking course)
808.8   | elements of literature (2)
808.8   | elements of literature (4)
813.6   | exhalation
448 ?   | passport D
338.9678 | states, markets, and institutional failure
823 ?   | the tiger of naples
305.48896073 | women, race & class
828.914 | writing home
"""

DEWEY_PATTERN = re.compile(r'^\d{3}(\.\d+)?$')


def normalize(title):
    text = unicodedata.normalize('NFC', title or '').replace('⁠', '')
    text = text.replace('’', "'").replace('‘', "'").replace('`', "'")
    return ' '.join(text.split()).casefold()


def load_classification():
    table, guesses = {}, set()
    for line in CLASSIFICATION.strip().splitlines():
        number, title = (part.strip() for part in line.split('|', 1))
        if number.endswith('?'):
            number = number.rstrip('? ').strip()
            guesses.add(normalize(title))
        if not DEWEY_PATTERN.match(number):
            raise ValueError(f'Bad Dewey number {number!r} for {title!r}')
        table[normalize(title)] = number
    return table, guesses


def main():
    parser = argparse.ArgumentParser(description='Set the Dewey number of every book in the catalogue.')
    parser.add_argument('--db', default=DEFAULT_DB, help='SQLite database file (default: %(default)s)')
    parser.add_argument('--dry-run', action='store_true', help='Show the changes without saving them')
    parser.add_argument('--overwrite', action='store_true', help='Replace Dewey numbers that are already set')
    args = parser.parse_args()
    if not os.path.exists(args.db):
        parser.error(f'Database not found: {args.db}')

    table, guesses = load_classification()
    conn = sqlite3.connect(args.db)
    cur = conn.cursor()
    for name in ('Book', 'DeletedBook'):
        cur.execute(f"PRAGMA table_info({name})")
        if 'dewey' not in {row[1].lower() for row in cur.fetchall()}:
            parser.error(f'{name}.dewey column is missing; run `python migrate_db.py` first')

    plan, unmatched, to_check = [], [], []
    for name in ('Book', 'DeletedBook'):
        cur.execute(f"SELECT title, dewey, COUNT(*) FROM {name} GROUP BY title, dewey ORDER BY title")
        for title, current, count in cur.fetchall():
            number = table.get(normalize(title))
            if number is None:
                if name == 'Book' and not current:
                    unmatched.append((title, count))
                continue
            if name == 'Book' and normalize(title) in guesses:
                to_check.append((number, title))
            if current and not args.overwrite:
                continue
            if current != number:
                plan.append((name, title, current, number, count))

    for name, title, current, number, count in plan:
        was = f' (was {current})' if current else ''
        print(f'{name}: {number:<14} {title}{was} [{count}]')
    if to_check:
        print(f'\n{len(to_check)} titles were classified from limited information; check them against the book:')
        for number, title in sorted(set(to_check), key=lambda item: item[1].casefold()):
            print(f'  {number:<14} {title}')
    if unmatched:
        print(f'\n{len(unmatched)} titles have no Dewey number in this script; set them in the app:')
        for title, count in unmatched:
            print(f'  {ascii(title)} [{count}]')

    total = sum(count for *_, count in plan)
    if not plan:
        print('\nNothing to change.')
    elif args.dry_run:
        print(f'\nDry run: {total} rows would change. Nothing saved.')
    else:
        backup = os.path.join(os.path.dirname(os.path.abspath(args.db)),
                              f"library_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db")
        shutil.copy2(args.db, backup)
        print(f'\nBackup saved: {backup}')
        with conn:
            for name, title, current, number, _ in plan:
                cur.execute(f"UPDATE {name} SET dewey=? WHERE title IS ? AND dewey IS ?", (number, title, current))
        print(f'Done: {total} rows updated.')

    cur.execute("SELECT SUBSTR(dewey, 1, 1) || '00', COUNT(DISTINCT title), COUNT(*) FROM Book "
                "WHERE dewey IS NOT NULL GROUP BY 1 ORDER BY 1")
    print('By Dewey class (titles / copies):',
          ', '.join(f'{cls} {titles}/{copies}' for cls, titles, copies in cur.fetchall()))
    conn.close()


if __name__ == '__main__':
    main()
