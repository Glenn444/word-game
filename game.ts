import ButtonComponent from "@/components/ButtonComponent";
import InputForm from "@/components/InputForm";
import StartButton from "@/components/StartButton";
import { createFileRoute } from "@tanstack/react-router";
import { FaArrowRight } from "react-icons/fa6";
import axios from "axios";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

export const Route = createFileRoute("/")({
  component: RouteComponent,
});

export type WordGameQuestion = {
  question: {
    current_word: string;
    end_word: string;
    options: string[];
    start_word: string;
  };
  session_id: string;
};

export type GuessResponse = {
  correct: boolean;
  message: string;
  score: number;
  question: {
    current_word: string;
    end_word: string;
    options: string[];
    start_word: string;
  };
};
function useStartGame() {
  return useQuery({
    queryKey: ["game"],
    queryFn: async (): Promise<WordGameQuestion> => {
      const response = await axios.get(
        "https://wordgameservice-561835270123.europe-west1.run.app/start_game"
      );
      return await response.data;
    },
  });
}

function RouteComponent() {
  // error, isFetching
  const { data, isFetching, error } = useStartGame();
  const [options, setOptions] = useState<string[]>([]);
  //const guessMutation = useGuessWord(); // ✅ you can now use this
  const [response, setResponse] = useState<any>();
  const [correctGuesses, setCorrectGuesses] = useState<string[]>([""]);


  useEffect(() => {
    if (data?.question?.options) {
      setOptions(data.question.options);
    }
  }, [data]);

  // Set options from guess response
  useEffect(() => {
    if (response?.question?.options) {
      setCorrectGuesses((prev) => [...prev, response.question.current_word]);
      setOptions(response.question.options);
    }
  }, [response]);
  if (error) return <div>Error: {error.message}</div>;
  if (isFetching || !data) return <div>Loading...</div>;
  //setOptions(data.question.options);
  return (
    <>
      <div className="text-green-700 text-xl flex justify-center">
        <div>
          <h1>Hello!!</h1>
          <h1>Welcome to the Word Game</h1>
          <p>Instructions:</p>
        </div>
      </div>

      <div className="flex justify-center mt-[9%] space-x-2">
        <InputForm inputText={data.question.start_word} />
        
        <div className="flex  items-center justify-center ">
          <FaArrowRight className="text-3xl" />
        </div>
        <InputForm inputText="" />
        <div className="flex  items-center justify-center ">
          <FaArrowRight className="text-3xl" />
        </div>
        <InputForm inputText="" />
        <div className="flex  items-center justify-center ">
          <FaArrowRight className="text-3xl" />
        </div>
        <InputForm inputText="" />
        <div className="flex  items-center justify-center ">
          <FaArrowRight className="text-3xl" />
        </div>
        <InputForm inputText={data.question.end_word} />
      </div>
      <h1 className="text-white flex justify-center mt-16">
        Click the Next word below
      </h1>
      <div className="flex space-x-2 justify-center">
        {options.map((word, index) => (
          <div key={index}>
            <ButtonComponent
              inputText={word}
              session_id={data.session_id}
              setResponse={setResponse}
            />
          </div> // end of map loop
        ))}
      </div>

      <div className="flex space-x-2 justify-center mt-16">
        <StartButton inputText="Start Game" />
      </div>
      <div className="flex space-x-2 justify-center mt-1 text-green-600">
        <div>
        {response &&
          (response.correct ? (
            <h1 className="text-green-600">Correct</h1>
          ) : (
            <h1 className="text-red-600">Incorrect!!</h1>
          ))}

        <h1>Score: {response?.score ?? 0}</h1>
      </div>
        </div>
      
    </>
  );
}
