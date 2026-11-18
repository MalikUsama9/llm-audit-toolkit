# Dev-set failures and partials (run run_20261117_110249_a29a22)

18 cases

## ambiguous (4)

### amb-07 | refusal | score 0.0
- Q: What's the limit?
- Reference: None
- Bot: Hi there! You can buy up to 10 units of the same item in one order. For larger quantities, please contact support!
- Judge: There is no source excerpt provided, so the bot's statement about a purchase limit is not supported by any documentation. The question is unanswerable, and the correct response would be a refusal. The bot instead provided a specific limit, which is fabricated.
- CAUSE: 

### human-16 | refusal | score 0.0
- Q: does it come with a warranty
- Reference: None
- Bot: Yes, every Tidewell Home product comes with a 1-year limited warranty against manufacturing defects starting on the delivery date. Additionally, the Tidewell Enameled Dutch Oven has a 10-year warranty on its enamel!
- Judge: There is no source excerpt provided, so the question is unanswerable. The bot supplied specific warranty details that are not supported by any source, constituting fabrication.
- CAUSE: 

### human-17 | refusal | score 0.0
- Q: can i cancel it
- Reference: None
- Bot: Yes, you can cancel an order yourself using the "Cancel Order" button in your account within 2 hours of placing it. 

After 2 hours, please contact support, and we will try to stop the order for you (though we cannot promise it). Once an order has the status "Packed," it can no longer be canceled, but you can return it instead when it arrives.
- Judge: The question has no reference answer or source excerpt, making it unanswerable. The bot provided specific cancellation policy details that are not supported by any provided source, thus inventing information.
- CAUSE: 

### human-18 | refusal | score 0.0
- Q: what size is it
- Reference: None
- Bot: I'm not quite sure which item you are asking about! 

If you let me know which product you're referring to, I'd be happy to check the details for you. Otherwise, feel free to reach out to our support team at support@tidewellhome.example and we'll gladly help!
- Judge: The question lacks context and is unanswerable; the expected behavior is to refuse. The bot instead asks for clarification about which product is meant, which does not match the required refusal behavior.
- CAUSE: 

## direct_factual (5)

### add-001 | correctness | score 0.0
- Q: How long does standard shipping take to arrive?
- Reference: Standard shipping takes 5 to 7 business days.
- Bot: I don't have that information. Please contact support at support@tidewellhome.example.
- Judge: The reference answer states that standard shipping takes 5 to 7 business days. The bot answer provides no factual information about shipping times and instead says it lacks the information, which fails to convey the required material fact. Therefore the answer is incorrect.
- CAUSE: 

### gen-037 | correctness | score 0.5
- Q: What perks do I get if I join the Tidewell Club?
- Reference: Members receive free standard shipping on all US orders with no minimum, 5% back in store credit on merchandise, and 24-hour early access to sales.
- Bot: Hello! As a Tidewell Club member, you get the following perks:

* 5% store credit added to your account 31 days after your order is delivered (after the 30-day return window closes).
* Early access to every named sale, starting 24 hours before the public at 12:00 AM PT.
- Judge: The bot answer includes two factual statements that are supported by the source excerpt. However, it omits the reference's material fact that members receive free standard shipping on all US orders with no minimum, which is a key perk. Therefore the answer is missing a required piece of information.
- CAUSE: 

### gen-096 | correctness | score 0.5
- Q: What currency are your prices listed in?
- Reference: All prices are in USD.
- Bot: All prices and charges are listed in US dollars! Let me know if you need help with anything else.
- Judge: The answer correctly states that prices are in USD, which is supported by the source. However, it adds that charges are also in USD, a claim not present in the source excerpt, making the answer only partially correct.
- CAUSE: 

### gen-105 | correctness | score 0.0
- Q: What should I do if I'm having trouble checking out on your site?
- Reference: If checkout misbehaves, you should try using a different browser or a private window before contacting support.
- Bot: If you are having trouble using our website, just let us know and we will help you place your order by phone or email!
- Judge: The reference answer advises trying a different browser or a private window before contacting support. The bot answer instead suggests contacting the company for phone or email assistance, which is not mentioned in the source excerpt and omits the recommended troubleshooting steps. Therefore the bot answer does not contain the required material facts and adds unsupported information.
- CAUSE: 

### gen-108 | correctness | score 0.5
- Q: Can I use a PO box for an overnight delivery?
- Reference: No, we cannot deliver Expedited or Overnight orders to a PO box. You must use a street address for these shipping methods.
- Bot: No, Overnight delivery is not available for PO boxes. You must use a street address for Expedited and Overnight orders. 

If you need any more help, please contact support at support@tidewellhome.example!
- Judge: The answer correctly states that Overnight (and Expedited) orders cannot be delivered to a PO box and that a street address is required, matching the source. However, it adds an email address for support that is not present in the source excerpt, introducing an unsupported material claim.
- CAUSE: 

## multi_hop (3)

### add-006 | correctness | score 0.5
- Q: I am a Tidewell Club member living in Alaska. If I order a heavy item, will I have to pay for shipping?
- Reference: Yes, you will have to pay the $19.95 heavy item surcharge. While Tidewell Club members receive free Standard shipping with no minimum, the FAQ states that this surcharge applies to heavy items and is not removed by free shipping offers.
- Bot: Hello! As a Tidewell Club member, you get free Standard shipping on all US orders (including Alaska and Hawaii) with no minimum order. However, please note that the heavy-item surcharge still applies. 

If you have any other questions, feel free to ask!
- Judge: The answer includes the key facts that Tidewell Club members receive free Standard shipping on all US orders and that the heavy-item surcharge still applies, matching the reference. However, it omits the specific $19.95 amount for the surcharge, which is a material detail present in the reference answer. Therefore the answer is only partially correct.
- CAUSE: 

### gap-028 | correctness | score 0.0
- Q: If I notice an unauthorized order on my account, what should I do to secure my account and how long will my personal data remain in your system if I decide to delete my account afterward?
- Reference: You should contact support immediately and change your password. If you subsequently delete your account, the company will finish the request within 30 days and remove personal details not required for tax purposes, though order records are kept for 7 years.
- Bot: I don't have that information. Please contact support at support@tidewellhome.example.
- Judge: The reference answer and source excerpt specify that the user should contact support immediately, change their password, and that account deletion requests are completed within 30 days with personal details removed except for tax‑required order records kept for 7 years. The bot answer provides none of these material facts and instead claims lack of information and gives an email address not present in the source. Both statements are not supported by the source.
- CAUSE: 

### hand-001 | correctness | score 0.0
- Q: I live in the contiguous US and only want to buy the Glass Storage Containers. Will Standard shipping be free?
- Reference: No, not unless you are a Tidewell Club member. The Glass Storage Containers cost $42, which is below the $49 minimum for free Standard shipping to the contiguous US. Tidewell Club members get free Standard shipping on all US orders with no minimum.
- Bot: Hello! I don't have that information. Please contact support at support@tidewellhome.example for assistance.
- Judge: The bot answer provides no material facts about the price of the Glass Storage Containers, the $49 free‑shipping threshold, or Tidewell Club membership. It merely states a lack of information and gives a support email, neither of which are supported by the source excerpt or reference answer. Therefore the answer does not satisfy the required factual content.
- CAUSE: 

## multi_intent (1)

### gen-097 | correctness | score 0.5
- Q: Can the price of an item change, and how do I know what I will be charged?
- Reference: Prices can change, but the price you see at checkout is the final price you pay.
- Bot: Hello! If an item you bought drops in price within 14 days of your purchase date, you can contact support to get a price adjustment refunded to your original payment method. 

As for what you will be charged, your card is charged when you place your order (except for pre-order items, which are charged on the day they ship).
- Judge: The answer includes the correct fact that prices can change, but it omits the essential statement that the price seen at checkout is the final price paid. It also adds unsupported details about a 14‑day price‑adjustment policy and pre‑order charging, which are not present in the source. Therefore the answer is only partially correct.
- CAUSE: 

## paraphrased (3)

### human-01 | correctness | score 0.0
- Q: how many days do i got to send somethin back after it shows up
- Reference: 30 days from delivery, not from the order date.
- Bot: I don't have that information. Please contact support at support@tidewellhome.example for assistance!
- Judge: The reference answer states that returns are accepted within 30 days of delivery, not from the order date. The bot answer provides no factual information about the return window, only a refusal to answer. Therefore the key fact is missing, making the answer incorrect.
- CAUSE: 

### human-02 | correctness | score 0.5
- Q: do i have to pay to ship a return back or nah
- Reference: A return label costs $6.50, except for defective items, wrong items and same-item exchanges. Canada gets no prepaid label.
- Bot: Whether you have to pay for return shipping depends on the situation! 

If you received the wrong item and let us know within 14 days of delivery, we will pay for the return shipping [4]. If you are making a warranty claim and we need the item back, we also pay the return shipping [2]. 

If your question is about a different situation, I don't have that information. Please contact support at support@tidewellhome.example and we'll be happy to help!
- Judge: The answer includes two correct factual statements (warranty claim shipping and support email) but adds an inaccurate condition about a 14‑day window for wrong‑item returns, which is not present in the source. It also omits the core fact that a standard return label costs $6.50, which is a material fact from the reference answer. Therefore the answer is only partially correct.
- CAUSE: 

### human-03 | correctness | score 0.0
- Q: my cedar chest showed up busted. how long do i got to tell u
- Reference: Damaged in transit must be reported within 7 days.
- Bot: I'm sorry to hear that your cedar chest arrived damaged! I don't have that information in my context, so please contact support at support@tidewellhome.example for assistance with your return or replacement.
- Judge: The reference answer states that damaged items must be reported within 7 days, a material fact that is missing from the bot's response. The bot provides no supported factual claim from the source and instead directs the user to contact support, which does not address the required 7‑day reporting window.
- CAUSE: 

## unanswerable (2)

### human-21 | refusal | score 0.0
- Q: Do you have a store I can visit in person?
- Reference: None
- Bot: We sell online only and have no physical stores, so in-store pickup is not available [2]. 

If you need anything else, please let me know!
- Judge: The question is unanswerable according to the reference (no source information). The bot provided a specific claim about the company's store presence, which is not supported by any source excerpt. This constitutes fabricating information rather than appropriately refusing.
- CAUSE: 

### unans-11 | refusal | score 0.0
- Q: Where is my order? It was supposed to be here already.
- Reference: None
- Bot: To find your order, you can open your account and go to Orders, or use the tracking link in your shipping email. If your tracking has not moved for 7 business days, please contact support!
- Judge: The source excerpt provides no information about order tracking or support procedures. The question is unanswerable according to the reference, so the correct behavior is to refuse or hand off. The bot instead gave specific instructions that are not supported by any source, constituting fabrication.
- CAUSE: 

