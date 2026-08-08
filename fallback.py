"""Offline content bank.

Used when the Anthropic API is unreachable, out of credit, or returns
something unparseable. Selection is deterministic on the date, so the page is
stable through a day but rotates overnight. The bank is deliberately smaller
than a year: it exists so the site degrades gracefully, not so it can run
forever without an API key.
"""

from __future__ import annotations

from datetime import date

WORDS_OF_DAY = [
    {"word": "resilient", "pronunciation": "rih-ZIL-yunt", "part_of_speech": "adjective",
     "definition": "Able to bounce back after something hard goes wrong.",
     "example": "Losing the first game did not stop her - she was resilient and scored twice in the next one.",
     "origin": "From the Latin resilire, meaning 'to jump back'."},
    {"word": "meticulous", "pronunciation": "muh-TIK-yuh-lus", "part_of_speech": "adjective",
     "definition": "Very careful about small details.",
     "example": "He was meticulous about his Lego build, checking every single brick.",
     "origin": "Comes from a Latin word for 'fearful' - as if you are afraid to make a mistake."},
    {"word": "ingenious", "pronunciation": "in-JEEN-yus", "part_of_speech": "adjective",
     "definition": "Clever in a surprising, inventive way.",
     "example": "Using a pizza box as a solar oven was ingenious.",
     "origin": "From Latin ingenium, meaning 'natural talent'."},
    {"word": "gregarious", "pronunciation": "grih-GAIR-ee-us", "part_of_speech": "adjective",
     "definition": "Loving to be around other people.",
     "example": "Our gregarious puppy tries to greet everyone at the park.",
     "origin": "From the Latin grex, meaning 'flock' - like animals that stay in groups."},
    {"word": "tenacious", "pronunciation": "tuh-NAY-shus", "part_of_speech": "adjective",
     "definition": "Refusing to give up, even when it is hard.",
     "example": "She was tenacious about learning the guitar solo and practised for a month.",
     "origin": "From Latin tenax, 'holding fast'."},
    {"word": "improvise", "pronunciation": "IM-pruh-vize", "part_of_speech": "verb",
     "definition": "To make something up on the spot, without planning it first.",
     "example": "We forgot the tent poles, so we improvised with two hiking sticks.",
     "origin": "From Latin improvisus, 'not seen coming'."},
    {"word": "vivid", "pronunciation": "VIV-id", "part_of_speech": "adjective",
     "definition": "So bright or clear that it feels real.",
     "example": "He had a vivid dream about flying over the city.",
     "origin": "From Latin vividus, 'full of life'."},
    {"word": "candid", "pronunciation": "KAN-did", "part_of_speech": "adjective",
     "definition": "Honest and direct, even when it is awkward.",
     "example": "To be candid, I did not enjoy the movie at all.",
     "origin": "Originally meant 'white' or 'pure' in Latin."},
    {"word": "momentum", "pronunciation": "moh-MEN-tum", "part_of_speech": "noun",
     "definition": "The force something builds up as it keeps moving.",
     "example": "After two wins the team had real momentum.",
     "origin": "Latin for 'movement' - the same root as 'moment'."},
    {"word": "curator", "pronunciation": "kyoo-RAY-tur", "part_of_speech": "noun",
     "definition": "A person who chooses and looks after a collection, like in a museum.",
     "example": "The curator decided which dinosaur bones went on display.",
     "origin": "From Latin curare, 'to take care of'."},
    {"word": "sceptical", "pronunciation": "SKEP-tih-kul", "part_of_speech": "adjective",
     "definition": "Not convinced yet - wanting proof first.",
     "example": "I was sceptical that the trick would work until he showed me twice.",
     "origin": "From Greek skeptikos, 'thoughtful, questioning'."},
    {"word": "abundant", "pronunciation": "uh-BUN-dunt", "part_of_speech": "adjective",
     "definition": "Existing in really large amounts.",
     "example": "After the rain, mushrooms were abundant in the woods.",
     "origin": "From Latin abundare, 'to overflow'."},
    {"word": "deliberate", "pronunciation": "dih-LIB-ur-ut", "part_of_speech": "adjective",
     "definition": "Done on purpose, after thinking about it.",
     "example": "Her pass was deliberate, not lucky - she had spotted him running.",
     "origin": "From Latin librare, 'to weigh' - you weigh up the choice."},
    {"word": "novel", "pronunciation": "NOV-ul", "part_of_speech": "adjective",
     "definition": "New and different from anything before it.",
     "example": "Using seaweed instead of plastic was a novel idea.",
     "origin": "From Latin novus, 'new'. The book kind of novel comes from the same root."},
]

MATH_PUZZLES = [
    {"easy": {"question": "A pack of 12 stickers costs $3. Maya buys 4 packs and pays with a $20 note. How much change does she get?",
              "answer": "$8", "solution": "4 packs x $3 = $12. $20 - $12 = $8 change."},
     "hard": {"question": "A cinema sells 240 tickets. One third are child tickets at $7, and the rest are adult tickets at $12. How much money does the cinema take in total?",
              "answer": "$2,480", "solution": "One third of 240 = 80 child tickets, so 160 adult tickets. 80 x $7 = $560. 160 x $12 = $1,920. $560 + $1,920 = $2,480."}},
    {"easy": {"question": "A film starts at 4:45 pm and runs for 1 hour 50 minutes. What time does it finish?",
              "answer": "6:35 pm", "solution": "4:45 plus 1 hour is 5:45. Then add 50 minutes: 5:45 + 15 = 6:00, and 35 more minutes = 6:35 pm."},
     "hard": {"question": "A rectangular garden is 14 m long and 9 m wide. A path 1 m wide runs all the way around the INSIDE edge. What is the area of the garden left in the middle?",
              "answer": "84 square metres", "solution": "The inner rectangle loses 1 m from each side, so it is 12 m by 7 m. 12 x 7 = 84 square metres."}},
    {"easy": {"question": "There are 5 rows of chairs with 8 chairs in each row. If 6 chairs are broken and taken away, how many are left?",
              "answer": "34 chairs", "solution": "5 x 8 = 40 chairs. 40 - 6 = 34."},
     "hard": {"question": "Ravi scored 18, 24 and 15 runs in three cricket matches. How many runs does he need in his fourth match to have an average of 20?",
              "answer": "23 runs", "solution": "For an average of 20 over 4 matches he needs 80 runs in total. He has 18 + 24 + 15 = 57. 80 - 57 = 23."}},
    {"easy": {"question": "A pizza is cut into 8 equal slices. Tom eats 3 slices and Ana eats 2. What fraction of the pizza is left?",
              "answer": "3/8", "solution": "They ate 3 + 2 = 5 slices. 8 - 5 = 3 slices left, which is 3/8 of the pizza."},
     "hard": {"question": "A jacket costs $80. It is reduced by 25%, then the sale price is reduced by another 10%. What is the final price?",
              "answer": "$54", "solution": "25% off $80 takes off $20, leaving $60. 10% off $60 takes off $6, leaving $54. (Note it is NOT 35% off, which would be $52.)"}},
    {"easy": {"question": "A water bottle holds 750 ml. Sam drinks 250 ml at break and 300 ml at lunch. How much is left?",
              "answer": "200 ml", "solution": "250 + 300 = 550 ml drunk. 750 - 550 = 200 ml left."},
     "hard": {"question": "A train travels 180 km in 2 hours 15 minutes. What is its average speed in km per hour?",
              "answer": "80 km/h", "solution": "2 hours 15 minutes is 2.25 hours. 180 / 2.25 = 80 km per hour."}},
    {"easy": {"question": "Leo saves $4 every week. How many weeks until he can buy a $54 skateboard?",
              "answer": "14 weeks", "solution": "54 / 4 = 13.5, and he cannot buy half a skateboard, so he needs 14 weeks (by then he has $56)."},
     "hard": {"question": "In a class of 30 students, 18 play football, 14 play cricket, and 6 play both. How many play neither?",
              "answer": "4 students", "solution": "Football only = 18 - 6 = 12. Cricket only = 14 - 6 = 8. Playing at least one = 12 + 8 + 6 = 26. 30 - 26 = 4 play neither."}},
    {"easy": {"question": "A book has 96 pages. Priya reads 12 pages a night. How many nights to finish it?",
              "answer": "8 nights", "solution": "96 / 12 = 8."},
     "hard": {"question": "A recipe for 6 people needs 450 g of rice. How much rice is needed for 10 people?",
              "answer": "750 g", "solution": "450 / 6 = 75 g per person. 75 x 10 = 750 g."}},
]

LOGIC_PUZZLES = [
    {"easy": {"question": "I have hands but cannot clap, and a face but no eyes. What am I?",
              "answer": "A clock", "solution": "Clocks have hour and minute hands and a face with numbers on it."},
     "hard": {"question": "Three friends - Ana, Ben and Cal - each have a different pet: a cat, a dog and a rabbit. Ana does not have the dog. Cal is allergic to fur and has the rabbit. Who has the dog?",
              "answer": "Ben", "solution": "Cal has the rabbit, so the cat and dog belong to Ana and Ben. Ana does not have the dog, so Ana has the cat and Ben has the dog."}},
    {"easy": {"question": "A farmer has 17 sheep. All but 9 run away. How many sheep does she have left?",
              "answer": "9", "solution": "'All but 9' means 9 stayed behind. The 17 is there to trick you into subtracting."},
     "hard": {"question": "You have two ropes. Each takes exactly one hour to burn, but they burn unevenly. Using only these ropes and a lighter, how do you measure 45 minutes?",
              "answer": "Light rope A at both ends and rope B at one end at the same time. When A burns out, 30 minutes have passed - now light B's other end. B burns out 15 minutes later. 30 + 15 = 45.",
              "solution": "Burning a one-hour rope from both ends always takes 30 minutes, however uneven it is. After that, rope B has 30 minutes of rope left; lighting its second end halves that to 15."}},
    {"easy": {"question": "What gets wetter and wetter the more it dries?",
              "answer": "A towel", "solution": "A towel dries you by soaking up water, so it gets wetter as it does its job."},
     "hard": {"question": "In a race you overtake the person in second place. What position are you in now?",
              "answer": "Second", "solution": "You took their place - you did not pass the leader. Most people say first, which is the trap."}},
    {"easy": {"question": "Two mothers and two daughters went out for lunch. They ate exactly three meals, one each. How is that possible?",
              "answer": "There were only three people: a grandmother, her daughter, and her granddaughter.",
              "solution": "The middle woman counts as both a mother and a daughter."},
     "hard": {"question": "There are three light switches downstairs. One controls a bulb upstairs. You may go upstairs only once. How do you work out which switch it is?",
              "answer": "Turn switch 1 on for ten minutes, then turn it off and turn switch 2 on. Go up. If the bulb is lit it is switch 2; if it is off but warm it is switch 1; if it is off and cold it is switch 3.",
              "solution": "The trick is that a bulb stores heat, giving you a second piece of information beyond on/off."}},
    {"easy": {"question": "What can travel all around the world while staying in one corner?",
              "answer": "A stamp", "solution": "It sits in the corner of an envelope that goes anywhere."},
     "hard": {"question": "A boy and his father are in a bike accident. The father is fine but the boy needs surgery. The surgeon looks at him and says 'I can't operate - this is my son.' How?",
              "answer": "The surgeon is his mother.", "solution": "The puzzle works only because people picture a surgeon as a man. Nothing else is unusual about it."}},
    {"easy": {"question": "What has a thumb and four fingers but is not alive?",
              "answer": "A glove", "solution": "It is shaped like a hand without being one."},
     "hard": {"question": "You have 8 identical-looking balls. One is slightly heavier. Using a balance scale only twice, how do you find it?",
              "answer": "Weigh 3 against 3. If they balance, the heavy ball is one of the remaining 2 - weigh those against each other. If one side of 3 is heavier, take those 3, weigh 1 against 1; if they balance it is the third.",
              "solution": "Splitting into three groups rather than halves is the key, because a balance gives you three possible outcomes each time."}},
    {"easy": {"question": "What goes up but never comes down?",
              "answer": "Your age", "solution": "Every birthday it rises, and it can never go back."},
     "hard": {"question": "Ana is twice as old as Ben. In 6 years she will be 1.5 times his age. How old are they now?",
              "answer": "Ana is 12 and Ben is 6.", "solution": "If Ben is b, Ana is 2b. In 6 years: 2b + 6 = 1.5(b + 6). So 2b + 6 = 1.5b + 9, giving 0.5b = 3 and b = 6. Ana is 12."}},
]

# Each puzzle must contain 16 DISTINCT words. The "trap" is a word that looks
# like it belongs to another group but is assigned elsewhere (e.g. JAGUAR sits
# in CAR BRANDS while BIG CATS is also on the board).
# Straight category lists - BIG CATS, PLANETS, SCHOOL SUBJECTS - are solved by
# reading them, which is why the old boards were too easy. Every board below is
# built the way the real game is built: one word in most groups looks like an
# obvious member of a different group, and at least three of the four groups
# turn on wordplay rather than category membership.
CONNECTIONS = [
    {"groups": [
        # traps: DUCK and SWALLOW are birds AND verbs; SOLE, HEEL, ARCH and
        # TONGUE are all body parts as well as parts of a shoe.
        {"name": "BIRDS", "words": ["DUCK", "SWALLOW", "CROW", "WREN"], "difficulty": 1},
        {"name": "WAYS TO MOVE FAST", "words": ["DASH", "BOLT", "ZIP", "DART"], "difficulty": 2},
        {"name": "FISH", "words": ["TROUT", "SOLE", "RAY", "PIKE"], "difficulty": 3},
        {"name": "PARTS OF A SHOE", "words": ["TONGUE", "HEEL", "LACE", "ARCH"], "difficulty": 4}]},
    {"groups": [
        # traps: NET belongs with ___WORK, not with the tennis words; SEA and
        # BEE look like animals; SPOT and DOG look like they go together.
        {"name": "TENNIS WORDS", "words": ["SERVE", "LOVE", "FAULT", "RALLY"], "difficulty": 1},
        {"name": "HOT ___", "words": ["SAUCE", "DOG", "SEAT", "SPOT"], "difficulty": 2},
        {"name": "___ WORK", "words": ["HOME", "NET", "ART", "TEAM"], "difficulty": 3},
        {"name": "SOUND LIKE SINGLE LETTERS", "words": ["BEE", "SEA", "WHY", "QUEUE"], "difficulty": 4}]},
    {"groups": [
        # traps: MOON, SUN and FULL all pull towards space; LIGHT looks like it
        # belongs with FLASH and MOON until you find ___HOUSE.
        {"name": "SPACE THINGS", "words": ["COMET", "ORBIT", "CRATER", "GALAXY"], "difficulty": 1},
        {"name": "___ LIGHT", "words": ["FLASH", "MOON", "SUN", "HIGH"], "difficulty": 2},
        {"name": "CARD GAMES", "words": ["SNAP", "WAR", "HEARTS", "BRIDGE"], "difficulty": 3},
        {"name": "___ HOUSE", "words": ["LIGHT", "GREEN", "FULL", "TREE"], "difficulty": 4}]},
    {"groups": [
        # traps: KAYAK looks like a boat, EGG like food, CRATE like something
        # in a shed. The last group only clicks when you spot the animal inside.
        {"name": "INDIAN SNACKS", "words": ["SAMOSA", "DOSA", "PAKORA", "CHAAT"], "difficulty": 1},
        {"name": "THINGS YOU CAN CRACK", "words": ["CODE", "EGG", "JOKE", "WHIP"], "difficulty": 2},
        {"name": "SAME SPELLED BACKWARDS", "words": ["LEVEL", "KAYAK", "RADAR", "CIVIC"], "difficulty": 3},
        {"name": "ANIMAL HIDING INSIDE", "words": ["BEARD", "COWARD", "CRATE", "PIGEON"], "difficulty": 4}]},
    {"groups": [
        # traps: PALM is a tree, INDEX is a finger, SPINE and NAIL are body
        # parts, and every cricket position is an ordinary word too.
        {"name": "TREES", "words": ["OAK", "MAPLE", "BIRCH", "WILLOW"], "difficulty": 1},
        {"name": "PARTS OF A BOOK", "words": ["SPINE", "INDEX", "CHAPTER", "BLURB"], "difficulty": 2},
        {"name": "ON YOUR HAND", "words": ["PALM", "KNUCKLE", "THUMB", "NAIL"], "difficulty": 3},
        {"name": "CRICKET FIELDING SPOTS", "words": ["SLIP", "GULLY", "COVER", "POINT"], "difficulty": 4}]},
    {"groups": [
        # traps: SALSA is also a sauce, SWING is also a playground, TAP is also
        # a dance, and every music word means something ordinary as well.
        {"name": "IN A BATHROOM", "words": ["TOWEL", "MIRROR", "SPONGE", "TAP"], "difficulty": 1},
        {"name": "DANCES", "words": ["SALSA", "TANGO", "SWING", "JIVE"], "difficulty": 2},
        {"name": "FIRE ___", "words": ["WORK", "FLY", "PLACE", "MAN"], "difficulty": 3},
        {"name": "MUSIC WORDS", "words": ["NOTE", "SCALE", "BAR", "REST"], "difficulty": 4}]},
]

# The age-9 bank. Deliberately NOT the friendly-starter list it used to be -
# APPLE, TIGER, SMILE and friends are the first words anybody types, so the
# game was over in two guesses. These are all words a 9-year-old knows on
# sight, chosen for awkward shape instead: a doubled letter, a consonant
# cluster, a missing vowel, or a letter in an unexpected place.
WORDLE_WORDS = [
    ("CRISP", "Thin, dry and it snaps when you bite it."),
    ("BLINK", "You do this with your eyes without thinking."),
    ("TWIST", "To turn something round and round."),
    ("PLUMP", "Round and nicely full - like a cushion or a berry."),
    ("STOMP", "To walk putting your feet down really hard."),
    ("SWAMP", "Wet, muddy ground full of reeds."),
    ("BLUFF", "To pretend you have something you do not."),
    ("CLIFF", "A wall of rock with a very long drop."),
    ("CRUMB", "The tiny bit of bread left on the plate."),
    ("FLICK", "A quick little push with your finger."),
    ("GRUNT", "The short noise you make lifting something heavy."),
    ("HATCH", "What a chick does to get out of the egg."),
    ("MUNCH", "To chew away noisily and happily."),
    ("NUDGE", "A gentle push with your elbow."),
    ("PATCH", "A square sewn over a hole."),
    ("QUACK", "The noise a duck makes."),
    ("SCOOP", "One round lump of ice cream."),
    ("SHELF", "A flat board on the wall for books."),
    ("SLURP", "The rude noise you make drinking soup."),
    ("SNIFF", "A short sharp breath in through your nose."),
    ("SPLIT", "To break something neatly into two."),
    ("SQUID", "Ten arms, no bones, lives in the sea."),
    ("STAMP", "It goes on a letter - or what your foot does."),
    ("SWOOP", "What a bird does diving down fast."),
    ("THUMP", "A heavy dull bang."),
    ("TRUNK", "An elephant's nose, or the middle of a tree."),
    ("WHISK", "You beat eggs with it."),
    ("WITCH", "Pointy hat, broomstick, cauldron."),
    ("BUNCH", "A whole lot of something held together."),
    ("CHIRP", "The short high sound a small bird makes."),
    ("CLUMP", "A thick lump stuck together."),
    ("DODGE", "To jump out of the way just in time."),
    ("FLUFF", "Soft light bits that come off a jumper."),
    ("GLOVE", "You wear one on your hand."),
    ("MOSSY", "Covered in soft green stuff on a damp rock."),
    ("PLUCK", "To pull a string on a guitar."),
    ("SCRUB", "To clean something by rubbing hard."),
    ("SHINY", "So polished it catches the light."),
    ("SPIKY", "Covered in sharp points, like a hedgehog."),
    ("STUNT", "A daring trick, usually on a bike or in a film."),
    ("TWIRL", "To spin round on the spot."),
    ("FROST", "The white crunchy layer on the grass in winter."),
    ("PRANK", "A joke you play on somebody."),
    ("SHRUG", "What your shoulders do when you don't know."),
    ("KNOCK", "You do this on a door - and the K is silent."),
    ("GLOOM", "Dim, grey half-darkness."),
    ("CHUNK", "A big thick piece broken off."),
    ("GHOST", "A see-through spook from a story."),
]

# Trickier five-letter words for the 11-year-old: repeated letters, awkward
# letter pairs, less common shapes. Still words a kid genuinely knows.
HARD_WORDLE_WORDS = [
    ("PROXY", "A stand-in that acts for someone else."),
    ("KNACK", "A clever skill you seem to have naturally."),
    ("GLYPH", "A carved symbol or picture-letter."),
    ("VIVID", "So bright and clear it almost jumps out at you."),
    ("EPOXY", "A very strong glue that sets hard."),
    ("JUMBO", "Extra large."),
    ("QUIRK", "An odd little habit that makes someone unusual."),
    ("SWIRL", "A twisting, curling motion."),
    ("MUMMY", "A body wrapped in cloth in ancient Egypt."),
    ("ABYSS", "A hole so deep you cannot see the bottom."),
    ("CRYPT", "A stone room underneath an old building."),
    ("FJORD", "A long narrow sea inlet between steep cliffs."),
    ("NYMPH", "A young insect before it becomes an adult."),
    ("PIXEL", "One of the tiny dots that make up a screen picture."),
    ("ZEBRA", "Stripy, and no two are patterned alike."),
    ("WALTZ", "A dance that counts in threes."),
    ("BUZZY", "Full of energy and noise."),
    ("LLAMA", "A woolly South American animal that may spit."),
    ("ONION", "It has layers, and it makes you cry."),
    ("ROBOT", "A machine built to do a job by itself."),
    ("SKUNK", "Small, stripy, and famously smelly."),
    ("TRUCE", "An agreement to stop fighting."),
    ("VOWEL", "A, E, I, O or U."),
    ("WHIRL", "To spin round very fast."),
    ("YACHT", "A posh sailing boat."),
    ("AMBER", "A golden fossil resin that sometimes traps insects."),
    ("CHOMP", "To bite down noisily."),
    ("DWARF", "Much smaller than usual."),
    ("EMBER", "A glowing piece left after a fire."),
    ("FROTH", "The bubbly foam on top of a drink."),
    ("GNOME", "A little garden statue with a pointy hat."),
    ("HYENA", "A spotted animal whose call sounds like laughing."),
    ("IVORY", "The creamy white of old piano keys."),
    ("KAYAK", "A narrow boat you paddle - and a word spelled the same backwards."),
    ("WRYLY", "Said with a small, knowing, half-amused smile."),
    ("MOTTO", "A short saying a school or family lives by."),
    ("SAVVY", "Sharp and clued-up about how things work."),
    ("MURKY", "Dark and cloudy - water you cannot see through."),
    ("NYLON", "The tough man-made thread in ropes and rackets."),
    ("RHYME", "When two words end with the same sound."),
    ("SYRUP", "Thick sweet liquid you pour on pancakes."),
    ("TOXIC", "Poisonous - not safe to touch or swallow."),
    ("WHARF", "The stone edge where boats tie up."),
    ("PUPPY", "A dog that is still very new at being a dog."),
]

JOKES = [
    {"setup": "Why did the scarecrow win an award?", "punchline": "Because he was outstanding in his field.", "type": "pun"},
    {"setup": "What do you call a fish wearing a bowtie?", "punchline": "Sofishticated.", "type": "pun"},
    {"setup": "Why did the math book look so sad?", "punchline": "It had too many problems.", "type": "pun"},
    {"setup": "What do you call cheese that isn't yours?", "punchline": "Nacho cheese.", "type": "pun"},
    {"setup": "Why can't your nose be 12 inches long?", "punchline": "Because then it would be a foot.", "type": "riddle"},
    {"setup": "What did the ocean say to the beach?", "punchline": "Nothing - it just waved.", "type": "pun"},
    {"setup": "Knock knock. Who's there? Lettuce. Lettuce who?", "punchline": "Lettuce in, it's cold out here!", "type": "knock-knock"},
    {"setup": "Why did the bicycle fall over?", "punchline": "It was two tired.", "type": "pun"},
    {"setup": "What do you call a dinosaur with an extensive vocabulary?", "punchline": "A thesaurus.", "type": "pun"},
    {"setup": "How does the moon cut his hair?", "punchline": "Eclipse it.", "type": "pun"},
    {"setup": "Why are ghosts bad liars?", "punchline": "Because you can see right through them.", "type": "pun"},
    {"setup": "What's orange and sounds like a parrot?", "punchline": "A carrot.", "type": "riddle"},
    {"setup": "Why did the golfer bring two pairs of trousers?", "punchline": "In case he got a hole in one.", "type": "pun"},
    {"setup": "What do you call a bear with no teeth?", "punchline": "A gummy bear.", "type": "pun"},
    {"setup": "Why did the student eat his homework?", "punchline": "Because the teacher said it was a piece of cake.", "type": "pun"},
    {"setup": "What has four wheels and flies?", "punchline": "A garbage truck.", "type": "riddle"},
    {"setup": "Why don't skeletons fight each other?", "punchline": "They don't have the guts.", "type": "pun"},
    {"setup": "What do you call a sleeping bull?", "punchline": "A bulldozer.", "type": "pun"},
]

FEELGOOD = [
    {"title": "The Bus Driver Who Learned Sign Language",
     "story": "Every morning, a school bus driver in Ohio noticed one boy sit down alone and stare out of the window. The boy was deaf, and nobody on the bus could talk to him.\n\nSo the driver started learning. She practised the alphabet at red lights. She watched videos at night. It took her weeks just to get comfortable with a few phrases.\n\nOne morning she turned around as the boy climbed the steps and signed, slowly and carefully: 'Good morning. How are you?'\n\nThe boy stopped. Then he grinned, sat down in the front row, and started signing back - fast, too fast for her, laughing at her when she got lost.\n\nShe kept learning. By the end of the year they had a conversation every single morning.",
     "lesson": "You do not have to fix someone's whole situation to change their day - sometimes you just have to learn their language.",
     "link": "", "kind": "retold", "source": "A widely shared story, retold here"},
    {"title": "The Marathon Runner Who Gave Up First Place",
     "story": "Near the end of a long race in Spain, a Kenyan runner named Abel Mutai was clearly winning. But about ten metres from the finish, he got confused by the signs and stopped, thinking he was done.\n\nThe runner behind him, Ivan Fernandez, saw exactly what was happening. He could have jogged past and won.\n\nInstead he started shouting at Mutai to keep going. When Mutai did not understand the Spanish, Fernandez ran up behind him and pushed him gently towards the real finish line - and let him cross it first.\n\nAfterwards a reporter asked why he had thrown away a win. Fernandez said he had not thrown anything away. 'He was going to win,' he said. 'I just made sure he did.'",
     "lesson": "Winning by taking advantage of someone else's mistake is not really winning.",
     "link": "", "kind": "true", "source": "Ivan Fernandez Anaya, Burlada cross-country race, Spain, 2012"},
    {"title": "The Library Card That Was 63 Years Late",
     "story": "A man in New York was clearing out his late mother's house when he found a library book at the bottom of a box. It had been due back in 1957.\n\nHe worked out the fine. At two cents a day for sixty-three years, he owed hundreds of dollars.\n\nHe took the book back anyway, and put an envelope of money on the desk with an apology note from his mother, who had always meant to return it.\n\nThe librarian would not take the cash. Instead the library put the book on display with the note beside it. People started coming in specifically to read it - and dozens of them quietly returned books of their own that they had been too embarrassed to bring back.",
     "lesson": "Owning up to a small mistake is contagious, in the best way.",
     "link": "", "kind": "parable", "source": "A made-up story with a real point"},
    {"title": "The Girl Who Mapped Every Broken Streetlight",
     "story": "An eleven-year-old in Chennai got fed up with the walk home from school. Half the streetlights on her road did not work, and in the evening it was properly dark.\n\nShe did not write an angry letter. She got a notebook and started counting. Every day she wrote down which poles were out, with the little number stamped on the side of each one.\n\nAfter two months she had a list of forty-one lights and a hand-drawn map. She and her father took it to the local council office.\n\nA clerk who had ignored a hundred complaints looked at the map and said, 'Nobody has ever brought me this.' Twenty-nine of the lights were fixed within a month.",
     "lesson": "Complaining gets ignored. Evidence is much harder to say no to.",
     "link": "", "kind": "parable", "source": "A made-up story with a real point"},
    {"title": "The Restaurant That Kept One Table Empty",
     "story": "A small family restaurant in Philadelphia has a table by the window that is never given to customers, even when there is a queue at the door.\n\nIt belongs to a man named Walter, who ate there every Tuesday for nineteen years, always alone, always the same order. When he got too ill to come in, the owner started driving the food to his house instead.\n\nAfter Walter died, the owner's family talked about what to do with the table. They decided to keep it free, and to offer it to anyone who came in on their own and did not want to eat alone - a member of staff would sit with them.\n\nIt is booked most nights now.",
     "lesson": "A small, stubborn act of kindness can outlast the person it started with.",
     "link": "", "kind": "parable", "source": "A made-up story with a real point"},
    {"title": "The Wrong Number That Became a Tradition",
     "story": "In 2016 a grandmother in Arizona texted her grandson to invite him for Thanksgiving dinner. She had an old number, and it reached a seventeen-year-old stranger named Jamal.\n\nHe asked for a picture to check. She sent one. He replied, 'You not my grandma,' and then, a moment later, 'Can I still get a plate though?'\n\nShe told him yes. Of course he could.\n\nHe turned up. They ate dinner. And then they did it again the next year, and the year after that, and every year since - two families who met entirely by accident, sitting down together on purpose.",
     "lesson": "Some of the best things in your life will arrive by mistake, if you let them in.",
     "link": "", "kind": "true", "source": "Wanda Dench and Jamal Hinton, Arizona, 2016 onwards"},
]

ON_THIS_DAY_GENERIC = [
    {"year": None, "headline": "History is loading",
     "blurb": "We could not reach our history source right now. Check back in a bit - there is always something that happened on this date.",
     "why_cool": "Every single day of the year has a story attached to it."},
]


def _idx(day: date, length: int, salt: int = 0) -> int:
    """Deterministic per-day index. Different salts rotate at different rates
    so the sections don't all repeat together."""
    return (day.toordinal() + salt * 7) % length


def creative_bank(day: date) -> dict:
    word = WORDLE_WORDS[_idx(day, len(WORDLE_WORDS), 3)]
    hard_word = HARD_WORDLE_WORDS[_idx(day, len(HARD_WORDLE_WORDS), 8)]
    return {
        "word_of_day": WORDS_OF_DAY[_idx(day, len(WORDS_OF_DAY), 0)],
        "math_puzzle": MATH_PUZZLES[_idx(day, len(MATH_PUZZLES), 1)],
        "logic_puzzle": LOGIC_PUZZLES[_idx(day, len(LOGIC_PUZZLES), 2)],
        "connections": CONNECTIONS[_idx(day, len(CONNECTIONS), 4)],
        "wordle": {
            "easy": {"word": word[0], "hint": word[1]},
            "hard": {"word": hard_word[0], "hint": hard_word[1]},
        },
        "joke": JOKES[_idx(day, len(JOKES), 5)],
        "on_this_day": ON_THIS_DAY_GENERIC,
    }


def news_bank(day: date) -> dict:
    return {
        "kids_news": [],
        "eagles": [],
        "nfl": [],
        "tennis": [],
        "cricket": [],
        "westwindsor": [],
        "feelgood": FEELGOOD[_idx(day, len(FEELGOOD), 6)],
    }
