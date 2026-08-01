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
CONNECTIONS = [
    {"groups": [
        {"name": "BIG CATS", "words": ["LION", "TIGER", "CHEETAH", "PANTHER"], "difficulty": 1},
        {"name": "PLANETS", "words": ["MARS", "VENUS", "SATURN", "NEPTUNE"], "difficulty": 2},
        {"name": "___ BALL", "words": ["BASE", "FOOT", "SNOW", "EYE"], "difficulty": 3},
        {"name": "CAR MODELS THAT ARE ANIMALS", "words": ["JAGUAR", "MUSTANG", "VIPER", "BEETLE"], "difficulty": 4}]},
    {"groups": [
        {"name": "THINGS IN A PENCIL CASE", "words": ["RULER", "ERASER", "SHARPENER", "GLUE"], "difficulty": 1},
        {"name": "BREAKFAST FOODS", "words": ["TOAST", "CEREAL", "WAFFLE", "BAGEL"], "difficulty": 2},
        {"name": "TENNIS TERMS", "words": ["SERVE", "RALLY", "LOVE", "SET"], "difficulty": 3},
        {"name": "WORDS BEFORE 'BACK'", "words": ["FEED", "PAPER", "COME", "HORSE"], "difficulty": 4}]},
    {"groups": [
        {"name": "MINECRAFT MOBS", "words": ["CREEPER", "ENDERMAN", "ZOMBIE", "SLIME"], "difficulty": 1},
        {"name": "OCEAN LIFE", "words": ["OTTER", "SQUID", "CORAL", "WHALE"], "difficulty": 2},
        {"name": "SHADES OF GREEN", "words": ["OLIVE", "LIME", "MINT", "FOREST"], "difficulty": 3},
        {"name": "ANIMATED MOVIE CHARACTERS", "words": ["NEMO", "SIMBA", "WOODY", "ELSA"], "difficulty": 4}]},
    {"groups": [
        {"name": "CRICKET WORDS", "words": ["WICKET", "OVER", "BOWLER", "INNINGS"], "difficulty": 1},
        {"name": "PARTS OF A BIKE", "words": ["PEDAL", "CHAIN", "SPOKE", "BRAKE"], "difficulty": 2},
        {"name": "THINGS YOU FOLD", "words": ["PAPER", "LAUNDRY", "MAP", "DOUGH"], "difficulty": 3},
        {"name": "WORN ON YOUR HEAD", "words": ["BEANIE", "HELMET", "CROWN", "CAP"], "difficulty": 4}]},
    {"groups": [
        {"name": "SCHOOL SUBJECTS", "words": ["MATH", "ART", "MUSIC", "SCIENCE"], "difficulty": 1},
        {"name": "WEATHER", "words": ["HAIL", "SLEET", "FOG", "BREEZE"], "difficulty": 2},
        {"name": "INDIAN FOODS", "words": ["DOSA", "SAMOSA", "PANEER", "CHAI"], "difficulty": 3},
        {"name": "SOMETHING VERY EASY", "words": ["CINCH", "SNAP", "PIECE", "DODDLE"], "difficulty": 4}]},
    {"groups": [
        {"name": "BIRDS", "words": ["ROBIN", "EAGLE", "SWALLOW", "PIGEON"], "difficulty": 1},
        {"name": "SPACE THINGS", "words": ["COMET", "ORBIT", "NEBULA", "ECLIPSE"], "difficulty": 2},
        {"name": "CONSTRUCTION MACHINES", "words": ["CRANE", "DIGGER", "LOADER", "ROLLER"], "difficulty": 3},
        {"name": "MARVEL CHARACTERS", "words": ["GROOT", "HULK", "THOR", "FALCON"], "difficulty": 4}]},
]

WORDLE_WORDS = [
    ("BRAVE", "How you feel when you do something scary anyway."),
    ("PLANT", "It grows in soil and needs sunlight."),
    ("CHESS", "A board game with kings, knights and bishops."),
    ("MANGO", "A sweet orange fruit, big in India."),
    ("STORM", "Thunder, lightning and lots of rain."),
    ("QUILT", "A warm blanket sewn from patches."),
    ("BEACH", "Sand, waves and a bucket and spade."),
    ("PIANO", "88 keys, black and white."),
    ("TIGER", "Orange with black stripes."),
    ("CLOUD", "White, fluffy and floating up high."),
    ("SKATE", "You do this on ice or on a board."),
    ("HONEY", "Bees make it and it is very sweet."),
    ("RIVER", "Water that flows all the way to the sea."),
    ("GHOST", "A see-through spook from a story."),
    ("PIZZA", "Round, cheesy, cut into slices."),
    ("SMILE", "What your face does when you are happy."),
    ("TRAIN", "It runs on rails and has carriages."),
    ("MONEY", "You keep it in a wallet."),
    ("LEMON", "Yellow and very sour."),
    ("BRUSH", "You use one on your teeth or your hair."),
    ("CROWN", "A king or queen wears it."),
    ("FLUTE", "A silver instrument you blow across."),
    ("SNAKE", "Long, scaly and has no legs."),
    ("WATCH", "It tells the time on your wrist."),
    ("EARTH", "The planet we live on."),
    ("GRAPE", "Small, round, grows in bunches."),
    ("KNIFE", "You use it to cut your food."),
    ("MOUSE", "Small squeaky animal - or the thing by your keyboard."),
    ("OCEAN", "Bigger than a sea, full of salt water."),
    ("PILOT", "The person flying the plane."),
    ("QUEEN", "She wears the crown."),
    ("ROBOT", "A machine that can move on its own."),
    ("SHARK", "A fish with a famous fin."),
    ("TOAST", "Bread that has been in the toaster."),
    ("VOICE", "What comes out when you speak or sing."),
    ("WHALE", "The biggest animal in the ocean."),
    ("ZEBRA", "Black and white stripes on the savanna."),
    ("APPLE", "Red or green, keeps the doctor away."),
    ("BREAD", "You make a sandwich out of it."),
    ("CHAIR", "You sit on it at the table."),
    ("DREAM", "The story your brain plays while you sleep."),
    ("FIELD", "Where a cricket or football match is played."),
    ("GIANT", "Enormous - or a big person in a fairy tale."),
    ("HEART", "It beats in your chest."),
    ("JUICE", "Squeezed out of an orange."),
    ("LIGHT", "You switch it on when it gets dark."),
    ("MEDAL", "You win it and hang it round your neck."),
    ("NIGHT", "When the sky goes dark."),
    ("PAINT", "You put it on a canvas with a brush."),
    ("SUGAR", "The sweet white stuff in a bowl."),
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
    return {
        "word_of_day": WORDS_OF_DAY[_idx(day, len(WORDS_OF_DAY), 0)],
        "math_puzzle": MATH_PUZZLES[_idx(day, len(MATH_PUZZLES), 1)],
        "logic_puzzle": LOGIC_PUZZLES[_idx(day, len(LOGIC_PUZZLES), 2)],
        "connections": CONNECTIONS[_idx(day, len(CONNECTIONS), 4)],
        "wordle": {"word": word[0], "hint": word[1]},
        "joke": JOKES[_idx(day, len(JOKES), 5)],
        "on_this_day": ON_THIS_DAY_GENERIC,
    }


def news_bank(day: date) -> dict:
    return {
        "kids_news": [],
        "eagles": [],
        "tennis": [],
        "cricket": [],
        "feelgood": FEELGOOD[_idx(day, len(FEELGOOD), 6)],
    }
